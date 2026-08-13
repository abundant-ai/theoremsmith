from __future__ import annotations

import asyncio
import io
import json
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock, Thread

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import shutil
import tempfile

from . import events, harbor, lean, oddish, pipeline, scan
from .config import Config
from .store import Store, new_id

cfg = Config.load()
store = Store(cfg.data_dir)
pool = ThreadPoolExecutor(max_workers=cfg.max_runs)
admission = Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    events.bind_loop(asyncio.get_running_loop())
    store.fail_orphans()
    if cfg.api_key:
        Thread(target=_prewarm_examples, daemon=True).start()
    yield
    pool.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="theoremsmith", lifespan=lifespan)

WEB = Path(__file__).parent / "web"
REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")


class NewRun(BaseModel):
    repo: str = Field(min_length=3, max_length=200)
    sha: str = ""
    goals: list[str] = []


def _repo(raw: str) -> str:
    raw = raw.strip().removesuffix(".git").removesuffix("/")
    raw = re.sub(r"^https?://github\.com/", "", raw)
    if not REPO_RE.match(raw):
        raise HTTPException(400, "repo must be owner/name on github.com")
    return raw


@app.get("/api/config")
def config() -> dict:
    return {"create_model": cfg.create_model,
            "configured": bool(cfg.api_key), "max_runs": cfg.max_runs,
            "examples": cfg.examples,
            "oddish_agent": cfg.oddish_agent, "oddish_model": cfg.oddish_model,
            "oddish_timeout": cfg.oddish_timeout,
            "oddish_available": oddish.available(cfg)}


class ScanRequest(BaseModel):
    repo: str = Field(min_length=3, max_length=200)
    sha: str = ""


def _scan(repo: str, sha: str, on_delta=lambda _p: None) -> list[scan.Option]:
    work = Path(tempfile.mkdtemp(prefix="theoremsmith-scan-", dir=cfg.data_dir))
    try:
        lean.clone(f"https://github.com/{repo}", sha, work / "src", lambda _l: None,
                   cfg.clone_timeout, shallow=True)
        return scan.scan_repo(cfg, repo, work / "src", on_delta=on_delta)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _prewarm_examples() -> None:
    for ex in cfg.examples:
        repo = ex.get("repo", "")
        if not REPO_RE.match(repo) or scan.read_cache(cfg, repo) is not None:
            continue
        try:
            scan.write_cache(cfg, repo, _scan(repo, ""))
        except Exception:
            continue


@app.post("/api/scan")
def scan_repo(body: ScanRequest) -> dict:
    if not cfg.api_key:
        raise HTTPException(400, "no API key is set on the server")
    repo = _repo(body.repo)
    sha = body.sha.strip()
    if not sha:
        cached = scan.read_cache(cfg, repo)
        if cached is not None:
            return {"repo": repo, "cached": True, "options": [o.__dict__ for o in cached]}
    try:
        options = _scan(repo, sha)
    except (lean.LeanError, scan.llm.LlmError) as exc:
        raise HTTPException(422, str(exc)[:300]) from exc
    if not sha:
        scan.write_cache(cfg, repo, options)
    return {"repo": repo, "cached": False, "options": [o.__dict__ for o in options]}


@app.post("/api/scan/prebuild")
def prebuild_examples() -> dict:
    if not cfg.api_key:
        raise HTTPException(400, "no API key is set on the server")
    Thread(target=_prewarm_examples, daemon=True).start()
    return {"warming": True,
            "cached": {ex["repo"]: scan.read_cache(cfg, ex["repo"]) is not None
                       for ex in cfg.examples if ex.get("repo")}}


@app.get("/api/scan/stream")
async def scan_stream(repo: str, sha: str = "") -> StreamingResponse:
    if not cfg.api_key:
        raise HTTPException(400, "no API key is set on the server")
    repo = _repo(repo)
    sha = sha.strip()

    async def gen():
        if not sha:
            cached = scan.read_cache(cfg, repo)
            if cached is not None:
                yield _sse({"options": [o.__dict__ for o in cached], "cached": True})
                return
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        put = lambda item: loop.call_soon_threadsafe(queue.put_nowait, item)

        def work():
            try:
                options = _scan(repo, sha, lambda piece: put({"text": piece}))
                if not sha:
                    scan.write_cache(cfg, repo, options)
                put({"options": [o.__dict__ for o in options]})
            except (lean.LeanError, scan.llm.LlmError) as exc:
                put({"error": str(exc)[:300]})
            except Exception as exc:  # noqa: BLE001
                put({"error": str(exc)[:200] or "the scan failed"})
            finally:
                put(None)

        loop.run_in_executor(None, work)
        yield _sse({"text": f"cloning {repo} and reading its theorems…\n"})
        while True:
            item = await queue.get()
            if item is None:
                break
            yield _sse(item)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/runs")
def list_runs() -> dict:
    return {"runs": store.list()}


@app.post("/api/runs")
def create_run(body: NewRun) -> dict:
    if not cfg.api_key:
        raise HTTPException(400, "THEOREMSMITH_API_KEY is not set on the server")
    repo = _repo(body.repo)
    goals = [g.strip() for g in body.goals if g.strip()]
    with admission:
        if store.active() >= cfg.max_runs:
            raise HTTPException(429, f"{cfg.max_runs} runs are already going; wait for one to finish")
        run = store.create(repo, body.sha.strip(), goals, False)
    pool.submit(pipeline.execute, cfg, store, run["id"])
    return run


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = store.read(run_id)
    if not run:
        raise HTTPException(404, "no such run")
    return run


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str) -> dict:
    if not store.delete(run_id):
        raise HTTPException(404, "no such run")
    return {"deleted": run_id}


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, after: int = 0) -> StreamingResponse:
    if not store.read(run_id):
        raise HTTPException(404, "no such run")
    queue = events.subscribe(run_id)

    async def gen():
        try:
            done, last = False, after
            for event in events.history(run_id, after):
                yield events.sse(event)
                done = done or event["kind"] == "end"
                last = max(last, event["seq"])
            if done:
                return
            if (store.read(run_id) or {}).get("status") in {"done", "failed"}:
                yield events.sse({"seq": last + 1, "t": 0, "kind": "end", "replayed": True})
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield events.sse(event)
                if event["kind"] == "end":
                    return
        finally:
            events.unsubscribe(run_id, queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


@app.get("/api/runs/{run_id}/solve/events")
async def solve_events(run_id: str) -> StreamingResponse:
    run = store.read(run_id)
    if not run:
        raise HTTPException(404, "no such run")
    info = (run.get("result") or {}).get("oddish") or {}
    task_id = info.get("task_id")
    if not task_id:
        raise HTTPException(409, "this run has not been sent to Oddish")
    if not oddish.available(cfg):
        raise HTTPException(503, f"the `{cfg.oddish_bin}` CLI is not on the server's PATH")

    # Prefer the trial resolved at submit; fall back to the newest, then index 0.
    trial_id = (info.get("trial_id")
                or oddish.resolve_trial(cfg, task_id)
                or f"{task_id}-0")

    async def gen():
        yield _sse({"text": f"following {info.get('agent')} / {info.get('model')} "
                            f"on Oddish (trial {trial_id})…"})
        proc = await asyncio.create_subprocess_exec(
            *oddish.logs_command(cfg, trial_id),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            async for raw in proc.stdout:
                text = oddish.clean_line(raw.decode("utf-8", "replace"))
                low = text.lower()
                if not text or "no live events" in low or "not found" in low:
                    continue
                yield _sse({"text": text})
        finally:
            if proc.returncode is None:
                proc.terminate()
                await proc.wait()
        yield _sse({"done": True})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/runs/{run_id}/task")
def download_task(run_id: str):
    run = store.read(run_id)
    if not run:
        raise HTTPException(404, "no such run")
    if run["status"] != "done":
        raise HTTPException(409, "this run did not finish, so its task is not offered")
    task = store.dir(run_id) / "task"
    if not task.exists():
        raise HTTPException(404, "this run has no task yet")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path in task.rglob("*"):
            if path.is_file() and ".lake" not in path.parts:
                z.write(path, path.relative_to(task.parent).as_posix())
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{run_id}-task.zip"'})


def _spawn(target, *args) -> None:
    Thread(target=target, args=args, daemon=True).start()


def _submit_to_oddish(run_id: str) -> None:
    run = store.read(run_id)
    if not run:
        return
    log = lambda line: events.emit(run_id, "log", text=str(line)[:2000], level="info")
    events.emit(run_id, "log", text=f"submitting to Oddish: {cfg.oddish_agent} / "
                f"{cfg.oddish_model}, {cfg.oddish_timeout // 60}-minute limit", level="info")
    # Oddish derives the task id from the packed dir name + content hash, so give
    # each submit a unique name and nonce — otherwise it collides with a prior
    # submit's task (and inherits its state, e.g. a cancelled task's dead S3 data).
    slug = (run.get("result") or {}).get("slug") or "theoremsmith"
    nonce = new_id()
    packed = store.dir(run_id) / f"{slug}-{nonce[:8]}"
    try:
        harbor.pack(cfg, store.dir(run_id) / "task", packed, nonce=nonce)
        info = oddish.submit(cfg, packed, log)
    except (oddish.OddishError, OSError, ValueError) as exc:
        events.emit(run_id, "log", text=f"Oddish submit failed: {exc}", level="error")
        run = store.read(run_id) or run
        run["result"] = {**(run["result"] or {}), "oddish_error": str(exc)[:400]}
        store.write(run)
        events.emit(run_id, "status", status=run.get("status"))
        return
    finally:
        shutil.rmtree(packed, ignore_errors=True)
    run = store.read(run_id) or run
    run["result"] = {**(run["result"] or {}), "oddish": info}
    store.write(run)
    events.emit(run_id, "log", text=f"Oddish run: {info['public_url']}", level="info")
    events.emit(run_id, "status", status=run.get("status"))


@app.post("/api/runs/{run_id}/submit")
def submit_to_oddish(run_id: str) -> dict:
    run = store.read(run_id)
    if not run:
        raise HTTPException(404, "no such run")
    if run["status"] != "done" or not (run.get("result") or {}).get("verified"):
        raise HTTPException(409, "only a finished, verified run can be sent to Oddish")
    if not (store.dir(run_id) / "task").exists():
        raise HTTPException(404, "this run has no task to submit")
    if not oddish.available(cfg):
        raise HTTPException(503, f"the `{cfg.oddish_bin}` CLI is not on the server's PATH")
    if (run.get("result") or {}).get("oddish_error"):
        run["result"].pop("oddish_error", None)
        store.write(run)
    # Upload to Oddish in the background so the click returns immediately; the public
    # link lands on the run (and its live view) when the upload finishes.
    _spawn(_submit_to_oddish, run_id)
    return {"submitting": True}


@app.get("/api/{rest:path}")
def unknown_api(rest: str) -> dict:
    raise HTTPException(404, f"no such endpoint: /api/{rest}")


if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        candidate = (WEB / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(WEB.resolve()):
            return FileResponse(candidate)
        return FileResponse(WEB / "index.html")

else:

    @app.get("/{path:path}")
    def no_web(path: str) -> dict:
        return {"detail": "the web build is missing; run `npm install && npm run build` in web/",
                "api": "/api/runs"}
