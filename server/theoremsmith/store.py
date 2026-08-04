from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from threading import Lock

STAGES = ["clone", "build", "probe", "select", "cut", "emit", "verify"]

ID_RE = re.compile(r"^[0-9a-f]{12}$")

_lock = Lock()


class BadRunId(ValueError):
    pass


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def check_id(run_id: str) -> str:
    if not ID_RE.match(run_id or ""):
        raise BadRunId(run_id)
    return run_id


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s[:48] or "run"


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.runs_dir = root / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def dir(self, run_id: str) -> Path:
        return self.runs_dir / check_id(run_id)

    def path(self, run_id: str) -> Path:
        return self.dir(run_id) / "run.json"

    def create(self, repo: str, sha: str, goals: list[str], whole_repo: bool) -> dict:
        run_id = new_id()
        run = {
            "id": run_id,
            "repo": repo,
            "sha": sha,
            "goals": goals,
            "whole_repo": whole_repo,
            "status": "queued",
            "stage": None,
            "stages": {s: "pending" for s in STAGES},
            "error": None,
            "created": time.time(),
            "updated": time.time(),
            "result": None,
        }
        self.dir(run_id).mkdir(parents=True, exist_ok=True)
        self.write(run)
        return run

    def write(self, run: dict) -> None:
        run["updated"] = time.time()
        p = self.path(run["id"])
        tmp = p.with_suffix(".tmp")
        with _lock:
            tmp.write_text(json.dumps(run, indent=2), encoding="utf-8")
            os.replace(tmp, p)

    def read(self, run_id: str) -> dict | None:
        try:
            p = self.path(run_id)
        except BadRunId:
            return None
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def list(self) -> list[dict]:
        keys = ("id", "repo", "sha", "status", "stage", "stages", "error", "created", "updated")
        out = []
        for d in sorted(self.runs_dir.iterdir()):
            run = self.read(d.name) if d.is_dir() else None
            if not run or "id" not in run:
                continue
            summary = {k: run.get(k) for k in keys}
            summary["stages"] = run.get("stages") or {s: "pending" for s in STAGES}
            summary["created"] = run.get("created") or 0
            summary["result"] = {"targets": (run.get("result") or {}).get("targets", [])}
            out.append(summary)
        return sorted(out, key=lambda r: r["created"], reverse=True)

    def active(self) -> int:
        return sum(1 for r in self.list() if r["status"] in {"queued", "running"})

    def delete(self, run_id: str) -> bool:
        import shutil
        try:
            d = self.dir(run_id)
        except BadRunId:
            return False
        if not d.exists():
            return False
        shutil.rmtree(d, ignore_errors=True)
        return True


    def fail_orphans(self) -> int:
        stranded = 0
        for summary in self.list():
            if summary["status"] not in {"queued", "running"}:
                continue
            run = self.read(summary["id"])
            if not run:
                continue
            run["status"] = "failed"
            run["error"] = "the server restarted while this run was in progress"
            for name, state in (run.get("stages") or {}).items():
                if state == "running":
                    run["stages"][name] = "failed"
            self.write(run)
            stranded += 1
        return stranded
