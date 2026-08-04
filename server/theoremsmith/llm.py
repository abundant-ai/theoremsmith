from __future__ import annotations

import json
from typing import Callable

import httpx

from .config import Config


class LlmError(RuntimeError):
    pass


def chat(cfg: Config, system: str, user: str, on_delta: Callable[[str], None],
         max_tokens: int = 4096, timeout: int = 600) -> str:
    if not cfg.api_key:
        raise LlmError("THEOREMSMITH_API_KEY is not set")
    payload = {
        "model": cfg.model,
        "stream": True,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    text: list[str] = []
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=30)) as client:
            with client.stream("POST", f"{cfg.base_url}/chat/completions", json=payload,
                               headers={"Authorization": f"Bearer {cfg.api_key}"}) as resp:
                if resp.status_code >= 400:
                    raise LlmError(f"{cfg.model} returned {resp.status_code}: "
                                   f"{resp.read().decode()[:400]}")
                for line in resp.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        break
                    try:
                        chunk = json.loads(body)
                    except json.JSONDecodeError:
                        continue
                    for choice in chunk.get("choices") or []:
                        piece = (choice.get("delta") or {}).get("content")
                        if piece:
                            text.append(piece)
                            on_delta(piece)
    except httpx.TimeoutException as exc:
        raise LlmError(f"{cfg.model} did not answer within {timeout}s") from exc
    except httpx.HTTPError as exc:
        raise LlmError(f"could not reach {cfg.base_url}: {exc}") from exc
    if not text:
        raise LlmError(f"{cfg.model} returned no content")
    return "".join(text)


def json_block(raw: str) -> dict:
    body = raw.strip()
    if "```" in body:
        parts = body.split("```")
        for part in parts:
            candidate = part.removeprefix("json").strip()
            if candidate.startswith("{"):
                body = candidate
                break
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise LlmError("the model did not return a JSON object")
    try:
        return json.loads(body[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LlmError(f"the model's JSON did not parse: {exc}") from exc
