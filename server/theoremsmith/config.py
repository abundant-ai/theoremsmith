from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Repositories offered as one-click starting points. Each is verified end to end:
# build -> cut -> the shipped grader gives the original proofs reward 1.
DEFAULT_EXAMPLES = [
    {"repo": "stepchowfun/proofs", "note": "tiny, plain-English facts"},
    {"repo": "leanprover-community/batteries", "note": "lists & trees, no mathlib"},
    {"repo": "leanprover/TensorLib", "note": "array & dtype facts, no mathlib"},
]


def _load_examples() -> list[dict]:
    raw = os.getenv("THEOREMSMITH_EXAMPLES", "").strip()
    if not raw:
        return DEFAULT_EXAMPLES
    out = []
    for item in raw.split(","):
        repo, _, note = item.strip().partition("|")
        if repo.strip():
            out.append({"repo": repo.strip(), "note": note.strip()})
    return out or DEFAULT_EXAMPLES


# Solvers offered in the "Run on Oddish" dialog. Every one runs under the same
# agent unless its own `agent` is given. Model ids are what `oddish run -m` takes;
# `claude-haiku-4-5` and `minimax-m3` are in Oddish's table. DeepSeek is NOT — so
# override with the exact provider id (e.g. `openrouter/deepseek/...`) via
# THEOREMSMITH_ODDISH_SOLVERS if the default does not resolve.
DEFAULT_SOLVERS = [
    {"label": "Claude Haiku 4.5", "agent": "claude-code", "model": "claude-haiku-4-5"},
    {"label": "DeepSeek V4 Flash", "agent": "claude-code", "model": "deepseek-v4-flash"},
    {"label": "MiniMax M3", "agent": "claude-code", "model": "minimax-m3"},
]


def _load_solvers() -> list[dict]:
    raw = os.getenv("THEOREMSMITH_ODDISH_SOLVERS", "").strip()
    if not raw:
        return DEFAULT_SOLVERS
    out = []
    for item in raw.split(","):
        parts = [p.strip() for p in item.split("|")]
        if len(parts) >= 2 and parts[0] and parts[1]:
            out.append({"label": parts[0], "model": parts[1],
                        "agent": parts[2] if len(parts) > 2 and parts[2] else "claude-code"})
    return out or DEFAULT_SOLVERS


@dataclass(frozen=True)
class Config:
    data_dir: Path
    base_url: str
    api_key: str
    create_model: str
    max_runs: int
    build_timeout: int
    probe_timeout: int
    clone_timeout: int
    examples: list[dict]
    oddish_bin: str = "oddish"
    oddish_agent: str = "claude-code"
    oddish_model: str = "claude-haiku-4-5"
    oddish_env: str = ""
    oddish_timeout: int = 1800
    oddish_submit_timeout: int = 600
    oddish_solvers: list[dict] = field(default_factory=lambda: list(DEFAULT_SOLVERS))

    @staticmethod
    def load() -> "Config":
        return Config(
            examples=_load_examples(),
            oddish_solvers=_load_solvers(),
            data_dir=Path(os.getenv("THEOREMSMITH_DATA", "./data")).resolve(),
            base_url=os.getenv("THEOREMSMITH_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            api_key=os.getenv("THEOREMSMITH_API_KEY") or os.getenv("OPENROUTER_API_KEY", ""),
            create_model=os.getenv("THEOREMSMITH_CREATE_MODEL", "moonshotai/kimi-k2.7-code"),
            max_runs=int(os.getenv("THEOREMSMITH_MAX_RUNS", "4")),
            build_timeout=int(os.getenv("THEOREMSMITH_BUILD_TIMEOUT", "3600")),
            probe_timeout=int(os.getenv("THEOREMSMITH_PROBE_TIMEOUT", "900")),
            clone_timeout=int(os.getenv("THEOREMSMITH_CLONE_TIMEOUT", "600")),
            oddish_bin=os.getenv("THEOREMSMITH_ODDISH_BIN", "oddish"),
            oddish_agent=os.getenv("THEOREMSMITH_ODDISH_AGENT", "claude-code"),
            oddish_model=os.getenv("THEOREMSMITH_ODDISH_MODEL", "claude-haiku-4-5"),
            oddish_env=os.getenv("THEOREMSMITH_ODDISH_ENV", ""),
            oddish_timeout=int(os.getenv("THEOREMSMITH_ODDISH_TIMEOUT", "1800")),
            oddish_submit_timeout=int(os.getenv("THEOREMSMITH_ODDISH_SUBMIT_TIMEOUT", "600")),
        )
