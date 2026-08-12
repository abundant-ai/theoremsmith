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


def resolve_trial(cfg: Config, task_id: str, max_probe: int = 24) -> str | None:
    """Return the newest trial of a task (`<task>-<n>`, highest existing index).

    Oddish reuses a task id for identical content and appends trials, so a fresh
    submit's trial is the highest index. `oddish logs <trial>` (no --follow) prints
    events or "No live events" for a real trial and "... not found" otherwise.
    """
    latest = None
    for n in range(max_probe):
        trial = f"{task_id}-{n}"
        try:
            proc = subprocess.run([cfg.oddish_bin, "logs", trial],
                                  capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            break
        if "not found" in ((proc.stdout or "") + (proc.stderr or "")).lower():
            break
        latest = trial
    return latest


def _extract_json(stdout: str) -> dict:
    """`oddish run --json` prints progress text around the JSON object; find it.

    Collect every top-level JSON object (raw_decode tolerates surrounding text and
    lets us skip nested objects), then prefer the one carrying the public link and
    otherwise return the last — so preamble/trailing lines don't break parsing.
    """
    text = stdout or ""
    decoder = json.JSONDecoder()
    objects: list[dict] = []
    idx = text.find("{")
    while idx != -1:
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx = text.find("{", idx + 1)
            continue
        if isinstance(obj, dict):
            objects.append(obj)
        idx = text.find("{", end)
    for obj in objects:
        if "public_experiment_url" in obj:
            return obj
    if objects:
        return objects[-1]
    raise OddishError(f"could not read oddish's response: {text[-400:]}")


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

    data = _extract_json(proc.stdout)

    public = data.get("public_experiment_url")
    if not public:
        raise OddishError("oddish accepted the task but returned no public link "
                          "(is publishing enabled for your account?)")
    tasks = data.get("tasks") or []
    task_id = tasks[0].get("id") if tasks else None
    trial_id = resolve_trial(cfg, task_id) if task_id else None
    return {
        "public_url": public,
        "experiment_url": data.get("experiment_url"),
        "experiment": data.get("experiment"),
        "task_id": task_id,
        "trial_id": trial_id,
        "agent": cfg.oddish_agent,
        "model": cfg.oddish_model,
    }
