from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    data_dir: Path
    base_url: str
    api_key: str
    create_model: str
    solve_model: str
    max_runs: int
    build_timeout: int
    probe_timeout: int
    clone_timeout: int

    @staticmethod
    def load() -> "Config":
        return Config(
            data_dir=Path(os.getenv("THEOREMSMITH_DATA", "./data")).resolve(),
            base_url=os.getenv("THEOREMSMITH_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            api_key=os.getenv("THEOREMSMITH_API_KEY") or os.getenv("OPENROUTER_API_KEY", ""),
            create_model=os.getenv("THEOREMSMITH_CREATE_MODEL", "moonshotai/kimi-k2.7-code"),
            solve_model=os.getenv("THEOREMSMITH_SOLVE_MODEL", "z-ai/glm-5.2"),
            max_runs=int(os.getenv("THEOREMSMITH_MAX_RUNS", "4")),
            build_timeout=int(os.getenv("THEOREMSMITH_BUILD_TIMEOUT", "3600")),
            probe_timeout=int(os.getenv("THEOREMSMITH_PROBE_TIMEOUT", "900")),
            clone_timeout=int(os.getenv("THEOREMSMITH_CLONE_TIMEOUT", "600")),
        )
