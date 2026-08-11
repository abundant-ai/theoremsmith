from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .config import Config

_MARKUP = re.compile(r"\[/?[a-z][a-z0-9 =#._-]*\]")


class OddishError(RuntimeError):
    pass


def available(cfg: Config) -> bool:
    return shutil.which(cfg.oddish_bin) is not None


def clean_line(line: str) -> str:
    """Strip Rich console markup (e.g. `[dim]…[/dim]`) from an `oddish logs` line."""
    return _MARKUP.sub("", line).rstrip()


def logs_command(cfg: Config, trial_id: str) -> list[str]:
    return [cfg.oddish_bin, "logs", trial_id, "--follow"]


def _command(cfg: Config, task_dir: Path) -> list[str]:
    cmd = [cfg.oddish_bin, "run", str(task_dir),
           "-a", cfg.oddish_agent, "-m", cfg.oddish_model,
           "--publish", "--background", "--json"]
    if cfg.oddish_env:
        cmd += ["--env", cfg.oddish_env]
    return cmd


def submit(cfg: Config, task_dir: Path, on_log: Callable[[str], None] = lambda _l: None) -> dict:
    if not available(cfg):
        raise OddishError(f"the `{cfg.oddish_bin}` CLI is not on the server's PATH")
    cmd = _command(cfg, task_dir)
    on_log(f"$ {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=cfg.oddish_submit_timeout)
    except FileNotFoundError as exc:
        raise OddishError(f"the `{cfg.oddish_bin}` CLI is not on the server's PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise OddishError(f"oddish did not respond within {cfg.oddish_submit_timeout}s") from exc

    for line in (proc.stderr or "").splitlines():
        if line.strip():
            on_log(line[:2000])
    if proc.returncode != 0:
        raise OddishError((proc.stderr or proc.stdout or "oddish run failed")[-600:].strip())

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise OddishError(f"could not read oddish's response: {(proc.stdout or '')[-400:]}") from exc

    public = data.get("public_experiment_url")
    if not public:
        raise OddishError("oddish accepted the task but returned no public link "
                          "(is publishing enabled for your account?)")
    tasks = data.get("tasks") or []
    return {
        "public_url": public,
        "experiment_url": data.get("experiment_url"),
        "experiment": data.get("experiment"),
        "task_id": tasks[0].get("id") if tasks else None,
        "agent": cfg.oddish_agent,
        "model": cfg.oddish_model,
    }
