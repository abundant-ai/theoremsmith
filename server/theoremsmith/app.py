from __future__ import annotations

import asyncio
import io
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import shutil
import tempfile

from . import events, lean, pipeline, scan
from .config import Config
from .store import Store

cfg = Config.load()
store = Store(cfg.data_dir)
pool = ThreadPoolExecutor(max_workers=cfg.max_runs)
admission = Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    events.bind_loop(asyncio.get_running_loop())
    store.fail_orphans()
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
    return {"create_model": cfg.create_model, "solve_model": cfg.solve_model,
            "configured": bool(cfg.api_key), "max_runs": cfg.max_runs}


class ScanRequest(BaseModel):
    repo: str = Field(min_length=3, max_length=200)
    sha: str = ""


@app.post("/api/scan")
def scan_repo(body: ScanRequest) -> dict:
    if not cfg.api_key:
        raise HTTPException(400, "no API key is set on the server")
    repo = _repo(body.repo)
    url = f"https://github.com/{repo}"
    work = Path(tempfile.mkdtemp(prefix="theoremsmith-scan-", dir=cfg.data_dir))
    try:
        lean.clone(url, body.sha.strip(), work / "src", lambda _l: None, cfg.clone_timeout,
                   shallow=True)
        options = scan.scan_repo(cfg, repo, work / "src")
    except (lean.LeanError, scan.llm.LlmError) as exc:
        raise HTTPException(422, str(exc)[:300]) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"repo": repo, "options": [o.__dict__ for o in options]}


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
