from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "theoremsmith.app:app",
        host=os.getenv("THEOREMSMITH_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        log_level=os.getenv("THEOREMSMITH_LOG", "info"),
    )


if __name__ == "__main__":
    main()
