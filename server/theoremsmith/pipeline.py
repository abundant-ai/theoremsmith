from __future__ import annotations

import os
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


def _model_log(rid: str, label: str):
    _log(rid, f"— builder model · {label} —", "model")
    buf = [""]

    def on_piece(piece: str) -> None:
        buf[0] += piece
        while "\n" in buf[0]:
            line, _, buf[0] = buf[0].partition("\n")
            _log(rid, line, "model")

    def flush() -> None:
        _log(rid, buf[0], "model")
        buf[0] = ""

    return on_piece, flush


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
    goals = run["goals"]
    if goals:
        _log(rid, f"targets given: {', '.join(goals)}")
        _stage(store, run, "probe", "done")
        _stage(store, run, "select", "done")
    else:
        rows = lean.probe(source, modules, [], sink, cfg.probe_timeout)
        graph = dagcut.build_graph(rows)
        _log(rid, f"{len(graph.nodes)} authored declarations in the dependency graph")
        _stage(store, run, "probe", "done")
        _stage(store, run, "select", "running")
        goals = _select(cfg, rid, run["repo"], graph)
        run["goals"] = goals
        store.write(run)
        _log(rid, f"targets: {', '.join(goals)}")
        _stage(store, run, "select", "done")

    _stage(store, run, "cut", "running")
    rows = lean.probe(source, modules, goals, sink, cfg.probe_timeout)
    graph = dagcut.build_graph(rows)
    statements = {r["name"]: (r.get("statement") or "")[:2000]
                  for r in rows if r.get("record") == "goal"}
    part = dagcut.partition(graph, goals)
    _log(rid, f"surface {len(part.surface)} · sealed {len(part.sealed)} · support {len(part.support)}")
    table = dagcut.spans(graph, part.cut, source)
    cut = dagcut.apply_cut(source, part, table)
    if not cut["slots"]:
        raise dagcut.CutError("no answer slots were produced")
    _log(rid, f"blanked {len(cut['slots'])} proofs across {len(cut['files'])} files")
    _stage(store, run, "cut", "done")

    _stage(store, run, "emit", "running")
    prose = _prose(cfg, rid, run["repo"], goals, statements)
    slug = slugify(f"{run['repo'].split('/')[-1]}-{goals[0].split('.')[-1]}")
    task_dir = work / "task"
    meta = emit.write_task(task_dir, source, slug=slug, prose=prose, slots=cut["slots"],
                           answers=cut["answers"], modules=modules,
                           repo=run["repo"], sha=run["sha"])
    run["result"] = {**meta, "slots": len(cut["slots"]),
                     "support": len(cut["slots"]) - len(goals), "statements": statements,
                     "glosses": run.get("glosses") or {}}
    store.write(run)
    _stage(store, run, "emit", "done")

    _stage(store, run, "verify", "running")
    ok, detail = _verify(cfg, task_dir, source, sink)
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
        theorems = sum(1 for r in graph.nodes.values() if r.get("kind") == "theorem")
        raise dagcut.CutError(
            f"nothing here is worth cutting: {len(graph.nodes)} declarations, {theorems} of them "
            "theorems, and none has a proof long enough or with enough in-repository dependencies. "
            "Try a repository that proves things, or name the theorems yourself when starting a run")
    listing = "\n".join(f"{c['name']}  deps={c['deps']}  lines={c['lines']}" for c in cands)
    on_piece, flush = _model_log(rid, "choosing theorems")
    raw = llm.chat(
        cfg, SELECT_SYSTEM,
        SELECT_USER.format(repo=repo, candidates=listing, limit=3), on_piece)
    flush()
    asked = [str(t) for t in llm.json_block(raw).get("targets", []) if t]
    picked = [t for t in asked if t in graph.nodes]
    for missing in [t for t in asked if t not in graph.nodes]:
        _log(rid, f"the model named {missing}, which is not in this repository's graph", "warn")
    if not picked:
        picked = [cands[0]["name"]]
        _log(rid, f"falling back to {picked[0]}, the candidate with the most proof dependencies",
             "warn")
    return picked[:3]


def _prose(cfg: Config, rid: str, repo: str, goals: list[str], statements: dict[str, str]) -> str:
    body = "\n\n".join(f"{g}:\n{statements.get(g, '(statement unavailable)')[:1200]}" for g in goals)
    on_piece, flush = _model_log(rid, "writing the task description")
    try:
        text = llm.chat(cfg, PROSE_SYSTEM, PROSE_USER.format(repo=repo, statements=body),
                        on_piece, max_tokens=700)
    except llm.LlmError as exc:
        events.emit(rid, "log", text=f"description unavailable ({exc})", level="warn")
        text = f"Proof targets taken from {repo}."
    flush()
    return text.strip()


def _verify(cfg: Config, task_dir: Path, warm: Path, sink) -> tuple[bool, str]:
    scratch = task_dir.parent / "verify"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir()
    try:
        for name in ("tests", "solution"):
            shutil.copytree(task_dir / name, scratch / name, symlinks=True)
        shutil.copytree(scratch / "solution", scratch / "answers", symlinks=True)
        (scratch / "environment").symlink_to(warm)
        env = {**os.environ, "THEOREMSMITH_LOGS": str(scratch / "logs"), **lean.lake_env(warm)}
        for step, budget in (("apply_answers.py", 300), ("grade.py", cfg.build_timeout)):
            proc = subprocess.run(["python3", str(scratch / "tests" / step)], cwd=str(scratch),
                                  capture_output=True, text=True, timeout=budget, env=env)
            for line in (proc.stdout or "").splitlines():
                sink(line)
            if proc.returncode != 0:
                return False, ((proc.stdout or "") + (proc.stderr or ""))[-800:]
        return True, "the shipped grader gives the original proofs reward 1"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
