from __future__ import annotations

import shutil
import subprocess
import traceback
from pathlib import Path

from . import dagcut, emit, events, lean, llm
from .config import Config
from .store import Store, slugify

SELECT_SYSTEM = (
    "You choose proof targets for a Lean 4 benchmark task. You are given theorems from one "
    "repository with their dependency counts. Pick the ones that make a hard but fair task: "
    "substantial results with real proofs, not one-line restatements or trivial wrappers. "
    "Reply with a JSON object only."
)

SELECT_USER = """Repository: {repo}

Candidate theorems (name, proof-step count, lines of proof):
{candidates}

Pick between 1 and {limit} of these as the proof targets. Prefer theorems whose proofs are long
and depend on several helper lemmas from this same repository, because those helpers get deleted
and the solver must rebuild them.

Reply with exactly this JSON and nothing else:
{{"targets": ["Full.Name.One", "Full.Name.Two"], "why": "one sentence"}}
"""

PROSE_SYSTEM = (
    "You write the opening paragraph of a benchmark task description for a Lean 4 proof task. "
    "Write for a competent Lean user. State what the repository is about and what the theorems "
    "say, in plain language. Two to four sentences. No preamble, no headings, no bullet points, "
    "no mention of being an AI, no restating the rules."
)

PROSE_USER = """Repository: {repo}

The solver must prove these theorems, whose proofs have been removed:

{statements}

Write the paragraph.
"""


def _stage(store: Store, run: dict, name: str, state: str) -> None:
    run["stages"][name] = state
    run["stage"] = name if state == "running" else run["stage"]
    store.write(run)
    events.emit(run["id"], "stage", stage=name, state=state)


def _log(run_id: str, line: str, level: str = "info") -> None:
    if line.strip():
        events.emit(run_id, "log", text=line[:4000], level=level)


def execute(cfg: Config, store: Store, run_id: str) -> None:
    run = store.read(run_id)
    if not run:
        return
    run["status"] = "running"
    store.write(run)
    events.emit(run_id, "status", status="running")
    work = store.dir(run_id)
    source = work / "source"
    try:
        _run(cfg, store, run, work, source)
        run = store.read(run_id) or run
        run["status"] = "done"
        run["stage"] = None
        store.write(run)
        events.emit(run_id, "status", status="done")
    except Exception as exc:
        run = store.read(run_id) or run
        run["status"] = "failed"
        run["error"] = str(exc)[:1000] or type(exc).__name__
        for name, state in run["stages"].items():
            if state == "running":
                run["stages"][name] = "failed"
        store.write(run)
        (work / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        events.emit(run_id, "status", status="failed", error=run["error"])
    finally:
        events.emit(run_id, "end")


def _run(cfg: Config, store: Store, run: dict, work: Path, source: Path) -> None:
    rid = run["id"]
    sink = lambda line: _log(rid, line)

    _stage(store, run, "clone", "running")
    if source.exists():
        shutil.rmtree(source)
    url = run["repo"] if run["repo"].startswith("https://") else f"https://github.com/{run['repo']}"
    head = lean.clone(url, run["sha"], source, sink, cfg.clone_timeout)
    run["sha"] = head
    _stage(store, run, "clone", "done")

    _stage(store, run, "build", "running")
    lean.build(source, sink, cfg.build_timeout)
    _stage(store, run, "build", "done")

    _stage(store, run, "probe", "running")
    package, modules = lean.package_modules(source)
    _log(rid, f"library {package}: {len(modules)} modules")
    rows = lean.probe(source, modules, [], sink, cfg.probe_timeout)
    graph = dagcut.build_graph(rows)
    _log(rid, f"{len(graph.nodes)} authored declarations in the dependency graph")
    _stage(store, run, "probe", "done")

    _stage(store, run, "select", "running")
    goals = run["goals"] or _select(cfg, rid, run["repo"], graph)
    run["goals"] = goals
    store.write(run)
    _log(rid, f"targets: {', '.join(goals)}")
    _stage(store, run, "select", "done")

    _stage(store, run, "cut", "running")
    rows = lean.probe(source, modules, goals, sink, cfg.probe_timeout)
    graph = dagcut.build_graph(rows)
    statements = {r["name"]: r.get("statement", "") for r in rows if r.get("record") == "goal"}
    part = dagcut.partition(graph, goals)
    _log(rid, f"surface {len(part.surface)} · sealed {len(part.sealed)} · deleted {len(part.delete)}")
    table = dagcut.spans(graph, part.targets | part.delete, source)
    cut = dagcut.apply_cut(source, part, table)
    if not cut["slots"]:
        raise dagcut.CutError("no answer slots were produced")
    _log(rid, f"blanked {len(cut['slots'])} proofs, deleted {cut['removed']} helper declarations")
    _stage(store, run, "cut", "done")

    _stage(store, run, "emit", "running")
    prose = _prose(cfg, rid, run["repo"], goals, statements)
    slug = slugify(f"{run['repo'].split('/')[-1]}-{goals[0].split('.')[-1]}")
    task_dir = work / "task"
    meta = emit.write_task(task_dir, source, slug=slug, prose=prose, slots=cut["slots"],
                           answers=cut["answers"], modules=modules,
                           repo=run["repo"], sha=run["sha"])
    run["result"] = {**meta, "slots": len(cut["slots"]), "deleted": cut["removed"],
                     "statements": statements}
    store.write(run)
    _stage(store, run, "emit", "done")

    _stage(store, run, "verify", "running")
    ok, detail = _verify(cfg, rid, task_dir, sink)
    run = store.read(rid) or run
    run["result"] = {**(run["result"] or {}), "verified": ok, "verify": detail}
    store.write(run)
    _stage(store, run, "verify", "done" if ok else "failed")
    if not ok:
        raise RuntimeError(f"oracle verification failed: {detail}")


def _candidates(graph: dagcut.Graph, limit: int = 60) -> list[dict]:
    every = []
    for name, row in graph.nodes.items():
        if row.get("kind") != "theorem":
            continue
        deps = len(graph.body.get(name, set()))
        span = int(row.get("endLine") or 0) - int(row.get("startLine") or 0) + 1
        if deps == 0 and span < 2:
            continue
        every.append({"name": name, "deps": deps, "lines": span})
    every.sort(key=lambda c: (c["deps"], c["lines"]), reverse=True)
    substantial = [c for c in every if c["deps"] >= 2 and c["lines"] >= 4]
    return (substantial or every)[:limit]


def _select(cfg: Config, rid: str, repo: str, graph: dagcut.Graph) -> list[str]:
    cands = _candidates(graph)
    if not cands:
        raise dagcut.CutError("no theorem in this repository has a proof worth cutting")
    listing = "\n".join(f"{c['name']}  deps={c['deps']}  lines={c['lines']}" for c in cands)
    events.emit(rid, "model", phase="select", state="start")
    raw = llm.chat(
        cfg, SELECT_SYSTEM,
        SELECT_USER.format(repo=repo, candidates=listing, limit=3),
        lambda piece: events.emit(rid, "delta", phase="select", text=piece))
    events.emit(rid, "model", phase="select", state="end")
    picked = [t for t in llm.json_block(raw).get("targets", []) if t in graph.nodes]
    if not picked:
        picked = [cands[0]["name"]]
    return picked[:3]


def _prose(cfg: Config, rid: str, repo: str, goals: list[str], statements: dict[str, str]) -> str:
    body = "\n\n".join(f"{g}:\n{statements.get(g, '(statement unavailable)')[:1200]}" for g in goals)
    events.emit(rid, "model", phase="describe", state="start")
    try:
        text = llm.chat(cfg, PROSE_SYSTEM, PROSE_USER.format(repo=repo, statements=body),
                        lambda piece: events.emit(rid, "delta", phase="describe", text=piece),
                        max_tokens=700)
    except llm.LlmError as exc:
        events.emit(rid, "log", text=f"description unavailable ({exc})", level="warn")
        text = f"Proof targets taken from {repo}."
    events.emit(rid, "model", phase="describe", state="end")
    return text.strip()


def _verify(cfg: Config, rid: str, task_dir: Path, sink) -> tuple[bool, str]:
    scratch = task_dir.parent / "verify"
    if scratch.exists():
        shutil.rmtree(scratch)
    shutil.copytree(task_dir, scratch, symlinks=True)
    try:
        for answer in (scratch / "solution").iterdir():
            shutil.copy(answer, scratch / "answers" / answer.name)
        proc = subprocess.run(["python3", str(scratch / "tests" / "apply_answers.py")],
                              cwd=str(scratch), capture_output=True, text=True, timeout=300)
        sink(proc.stdout.strip())
        if proc.returncode != 0:
            return False, (proc.stdout + proc.stderr)[-800:]
        env = scratch / "environment"
        if lean.stream(["lake", "build"], env, sink, cfg.build_timeout, lean.lake_env(env)) != 0:
            return False, "the original proofs do not rebuild the repository"
        return True, "the original proofs rebuild the repository"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
