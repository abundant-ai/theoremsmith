from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from threading import Lock

STAGES = ["clone", "build", "probe", "select", "cut", "emit", "verify"]

_lock = Lock()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s[:48] or "run"


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.runs_dir = root / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

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
        p = self.path(run_id)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def list(self) -> list[dict]:
        out = []
        for d in self.runs_dir.iterdir():
            if not d.is_dir():
                continue
            run = self.read(d.name)
            if run:
                out.append({k: run[k] for k in
                            ("id", "repo", "sha", "status", "stage", "stages", "error", "created", "updated")})
        return sorted(out, key=lambda r: r["created"], reverse=True)

    def active(self) -> int:
        return sum(1 for r in self.list() if r["status"] in {"queued", "running"})

    def delete(self, run_id: str) -> bool:
        import shutil
        d = self.dir(run_id)
        if not d.exists():
            return False
        shutil.rmtree(d, ignore_errors=True)
        return True
