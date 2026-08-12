from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .config import Config

DOCKERFILE = """FROM ubuntu:24.04
ARG DEBIAN_FRONTEND=noninteractive
ENV PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

RUN apt-get update && apt-get install -y \\
    build-essential pkg-config ca-certificates git curl gpg python3 \\
 && rm -rf /var/lib/apt/lists/*

RUN curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \\
    | sh -s -- -y --default-toolchain none
ENV PATH="/root/.elan/bin:${PATH}"

WORKDIR /app
COPY repo /opt/theoremsmith/environment
RUN elan toolchain install "$(cat /opt/theoremsmith/environment/lean-toolchain)" || true
RUN cd /opt/theoremsmith/environment && (lake exe cache get || true) && (lake build || true)
RUN cp -a /opt/theoremsmith/environment /app/environment \\
 && chmod -R u+w /app/environment \\
 && chmod -R a-w /opt/theoremsmith/environment
COPY answers /app/answers
RUN chmod -R u+w /app/answers
RUN rm -rf /root/.cache /var/lib/apt/lists/*
CMD ["/bin/bash"]
"""

# The Harbor verifier. It runs in the agent container with the real grader mounted
# read-only at /tests, rebuilds the task tree from the sealed pre-agent environment
# plus the agent's answers, and lets the unchanged grader write /logs/verifier/reward.txt.
TEST_SH = """#!/bin/bash
set -o pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
export PATH="/root/.elan/bin:/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export THEOREMSMITH_LOGS=/logs/verifier

work=/logs/verifier/grade
rm -rf "$work"
mkdir -p "$work/answers"
cp -a /opt/theoremsmith/environment "$work/environment"
chmod -R u+w "$work/environment"
cp -a /app/answers/. "$work/answers/" 2>/dev/null || true
cp -a /tests/. "$work/tests/"

cd "$work" && bash "$work/tests/run_test.sh"
echo "reward: $(cat /logs/verifier/reward.txt 2>/dev/null)"
"""

TASK_TOML = """version = "1.0"

[metadata]
difficulty = "hard"
category = "formal-verification"
tags = ["formal-verification", "lean4"]
description = "{description}"
source_repo = "{repo}"
source_sha = "{sha}"
run_nonce = "{nonce}"
open_internet_justification = "Setup and verification install the pinned Lean toolchain and build the package from public sources; the agent phase is no-network, so the upstream repository and its proofs are unreachable while solving."

[verifier]
timeout_sec = {verifier_timeout}.0
network_mode = "public"

[agent]
timeout_sec = {agent_timeout}.0
network_mode = "no-network"

[environment]
build_timeout_sec = {build_timeout}.0
network_mode = "public"
cpus = 4
memory_mb = 16384
storage_mb = 16384
gpus = 0
"""


def _toml_str(text: str, limit: int = 200) -> str:
    return re.sub(r"\s+", " ", text or "").replace('"', "'").replace("\\", "/").strip()[:limit]


def _dereference(root: Path) -> None:
    """Replace every symlink under `root` with its target's bytes.

    A repo may ship a symlink (e.g. stepchowfun/proofs' `_CoqProject -> _RocqProject`)
    and Oddish's task upload refuses links ("links not allowed"). Reading through the
    link and rewriting a real file keeps valid content; a broken or non-file link
    (which would fail the build anyway) is dropped.
    """
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not path.is_symlink():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            path.unlink()
            continue
        path.unlink()
        path.write_bytes(data)


def pack(cfg: Config, task_dir: Path, dest: Path, *, nonce: str = "") -> Path:
    """Assemble a Harbor/oddish-runnable task from a finished run's task directory.

    The emitted theoremsmith format is left untouched; this reshapes a copy of it
    into `dest`, which `oddish run` accepts. `nonce` is written into task.toml so
    each submit is a distinct Oddish task (Oddish content-addresses the task id, so
    identical content would otherwise collide with — and inherit the fate of — a
    previous submit's task, e.g. one that was cancelled).
    """
    meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    if dest.exists():
        shutil.rmtree(dest)
    env = dest / "environment"
    env.mkdir(parents=True)

    ignore = shutil.ignore_patterns(".git", ".lake", "build", "*.olean")
    shutil.copytree(task_dir / "environment", env / "repo", symlinks=True, ignore=ignore)
    shutil.copytree(task_dir / "answers", env / "answers", symlinks=True)
    (env / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")
    (env / ".dockerignore").write_text("**/.git\n**/.lake\n**/build\n", encoding="utf-8")

    shutil.copytree(task_dir / "tests", dest / "tests", symlinks=True)
    test_sh = dest / "tests" / "test.sh"
    test_sh.write_text(TEST_SH, encoding="utf-8")
    test_sh.chmod(0o755)

    shutil.copy2(task_dir / "instruction.md", dest / "instruction.md")

    description = _toml_str(f"Fill the removed Lean 4 proofs in {meta.get('repo', '')}: "
                            f"{', '.join(meta.get('targets') or [])}")
    (dest / "task.toml").write_text(
        TASK_TOML.format(
            description=description,
            repo=_toml_str(meta.get("repo", ""), 120),
            sha=_toml_str(meta.get("sha", ""), 60),
            nonce=_toml_str(nonce, 64),
            verifier_timeout=cfg.build_timeout,
            agent_timeout=cfg.oddish_timeout,
            build_timeout=cfg.build_timeout,
        ),
        encoding="utf-8",
    )
    _dereference(dest)
    return dest
