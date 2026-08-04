from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

ASSETS = Path(__file__).parent / "assets"

Sink = Callable[[str], None]


class LeanError(RuntimeError):
    pass


def stream(argv: list[str], cwd: Path, sink: Sink, timeout: int, env: dict | None = None) -> int:
    proc = subprocess.Popen(
        argv, cwd=str(cwd), env=env or os.environ.copy(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            sink(line.rstrip("\n"))
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise LeanError(f"{argv[0]} exceeded {timeout}s")
    finally:
        if proc.poll() is None:
            proc.kill()


def clone(url: str, sha: str, dest: Path, sink: Sink, timeout: int) -> str:
    dest.mkdir(parents=True, exist_ok=True)
    if stream(["git", "clone", "--filter=blob:none", url, str(dest)], dest.parent, sink, timeout) != 0:
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


def build(root: Path, sink: Sink, timeout: int) -> None:
    env = lake_env(root)
    if not (root / "lakefile.lean").exists() and not (root / "lakefile.toml").exists():
        raise LeanError("not a Lake package: no lakefile.lean or lakefile.toml at the repo root")
    stream(["lake", "exe", "cache", "get"], root, sink, min(timeout, 900), env)
    if stream(["lake", "build"], root, sink, timeout, env) != 0:
        raise LeanError("lake build failed")


_LIB_RE = re.compile(r"^\s*lean_lib\s+«?([A-Za-z0-9_.]+)»?", re.M)


def package_modules(root: Path) -> tuple[str, list[str]]:
    text = ""
    for name in ("lakefile.lean", "lakefile.toml"):
        p = root / name
        if p.exists():
            text += p.read_text(encoding="utf-8", errors="replace")
    libs = _LIB_RE.findall(text)
    libs += re.findall(r'name\s*=\s*"([A-Za-z0-9_.]+)"', text)
    seen: list[str] = []
    for lib in libs:
        if lib not in seen and (root / lib).is_dir() or (root / f"{lib}.lean").exists():
            if lib not in seen:
                seen.append(lib)
    if not seen:
        for child in sorted(root.iterdir()):
            if child.is_dir() and any(child.rglob("*.lean")) and child.name[0].isupper():
                seen.append(child.name)
    if not seen:
        raise LeanError("could not find a Lean library root in this repo")
    package = seen[0]
    mods: list[str] = []
    base = root / package
    if (root / f"{package}.lean").exists():
        mods.append(package)
    if base.is_dir():
        for f in sorted(base.rglob("*.lean")):
            rel = f.relative_to(root).with_suffix("")
            mods.append(".".join(rel.parts))
    if not mods:
        raise LeanError(f"library {package!r} has no .lean modules")
    return package, mods


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
