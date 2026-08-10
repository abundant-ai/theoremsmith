from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

ASSETS = Path(__file__).parent / "assets"

Sink = Callable[[str], None]
_EOF = object()


class LeanError(RuntimeError):
    pass


def stream(argv: list[str], cwd: Path, sink: Sink, timeout: int, env: dict | None = None) -> int:
    proc = subprocess.Popen(
        argv, cwd=str(cwd), env=env or os.environ.copy(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    assert proc.stdout is not None
    lines: queue.Queue = queue.Queue(maxsize=10000)

    def pump() -> None:
        try:
            for line in proc.stdout:
                try:
                    lines.put(line.rstrip("\n"), timeout=1)
                except queue.Full:
                    pass
        finally:
            lines.put(_EOF)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    try:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise LeanError(f"{argv[0]} exceeded {timeout}s")
            try:
                line = lines.get(timeout=min(left, 5))
            except queue.Empty:
                continue
            if line is _EOF:
                break
            sink(line)
        return proc.wait(timeout=max(1, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        raise LeanError(f"{argv[0]} exceeded {timeout}s")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)


def clone(url: str, sha: str, dest: Path, sink: Sink, timeout: int, shallow: bool = False) -> str:
    dest.mkdir(parents=True, exist_ok=True)
    argv = ["git", "clone", "--filter=blob:none"]
    if shallow and not sha:
        argv += ["--depth", "1"]
    if stream([*argv, url, str(dest)], dest.parent, sink, timeout) != 0:
        raise LeanError(f"clone failed: {url}")
    if sha:
        if stream(["git", "checkout", "--detach", sha], dest, sink, timeout) != 0:
            raise LeanError(f"checkout failed: {sha}")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(dest),
                          capture_output=True, text=True).stdout.strip()
    return head


def lake_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("ELAN_HOME", str(Path.home() / ".elan"))
    env["PATH"] = f"{env['ELAN_HOME']}/bin:{env.get('PATH', '')}"
    env["LEAN_NUM_THREADS"] = env.get("LEAN_NUM_THREADS", "4")
    return env


def uses_mathlib(root: Path) -> bool:
    for name in ("lakefile.lean", "lakefile.toml", "lake-manifest.json"):
        path = root / name
        if path.exists() and "mathlib" in path.read_text(encoding="utf-8", errors="replace").lower():
            return True
    return False


def build(root: Path, sink: Sink, timeout: int) -> None:
    if not (root / "lakefile.lean").exists() and not (root / "lakefile.toml").exists():
        raise LeanError("not a Lake package: no lakefile.lean or lakefile.toml at the repo root")
    env = lake_env(root)
    if uses_mathlib(root):
        sink("fetching the mathlib build cache")
        stream(["lake", "exe", "cache", "get"], root, sink, min(timeout, 1800), env)
    if stream(["lake", "build"], root, sink, timeout, env) != 0:
        raise LeanError("lake build failed")


_LIB_LEAN = re.compile(r"^\s*lean_lib\s+«?([A-Za-z0-9_.']+)»?", re.M)
_LIB_TOML = re.compile(r"\[\[lean_lib\]\](.*?)(?=\n\[|\Z)", re.S)
_NAME = re.compile(r'^\s*name\s*=\s*"?([A-Za-z0-9_.]+)"?\s*$', re.M)


def library_names(root: Path) -> list[str]:
    names: list[str] = []
    lean_file = root / "lakefile.lean"
    if lean_file.exists():
        names += _LIB_LEAN.findall(lean_file.read_text(encoding="utf-8", errors="replace"))
    toml_file = root / "lakefile.toml"
    if toml_file.exists():
        text = toml_file.read_text(encoding="utf-8", errors="replace")
        for block in _LIB_TOML.findall(text):
            names += _NAME.findall(block)
        names += _NAME.findall(text.split("[[")[0])
    for child in sorted(root.iterdir()):
        if child.is_dir() and child.name[0].isupper() and any(child.rglob("*.lean")):
            names.append(child.name)
    out: list[str] = []
    for name in names:
        if name in out:
            continue
        if (root / name).is_dir() or (root / f"{name}.lean").exists():
            out.append(name)
    return out


def modules_of(root: Path, library: str) -> list[str]:
    mods: list[str] = []
    if (root / f"{library}.lean").exists():
        mods.append(library)
    base = root / library
    if base.is_dir():
        for f in sorted(base.rglob("*.lean")):
            mods.append(".".join(f.relative_to(root).with_suffix("").parts))
    return mods


def package_modules(root: Path) -> tuple[str, list[str]]:
    libs = library_names(root)
    if not libs:
        raise LeanError("could not find a Lean library in this repository")
    best = max(libs, key=lambda lib: len(modules_of(root, lib)))
    mods = modules_of(root, best)
    if not mods:
        raise LeanError(f"library {best!r} has no .lean modules")
    return best, mods


def probe(root: Path, modules: list[str], goals: list[str], sink: Sink, timeout: int) -> list[dict]:
    out_dir = Path(tempfile.mkdtemp(prefix="theoremsmith-probe-"))
    script = out_dir / "dag_probe.lean"
    jsonl = out_dir / "dag.jsonl"
    script.write_text((ASSETS / "dag_probe.lean").read_text(encoding="utf-8"), encoding="utf-8")
    argv = ["lake", "env", "lean", "-DmaxRecDepth=100000", "--run", str(script),
            ",".join(modules), str(jsonl), *goals]
    rc = stream(argv, root, sink, timeout, lake_env(root))
    if rc != 0:
        raise LeanError(f"probe exited {rc}")
    rows: list[dict] = []
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        raise LeanError("probe produced no declarations")
    return rows
