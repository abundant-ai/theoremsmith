from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque
from typing import Any

_HISTORY = 4000

_log: dict[str, deque] = defaultdict(lambda: deque(maxlen=_HISTORY))
_subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
_seq: dict[str, int] = defaultdict(int)
_loop: asyncio.AbstractEventLoop | None = None


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def emit(run_id: str, kind: str, **fields: Any) -> None:
    _seq[run_id] += 1
    event = {"seq": _seq[run_id], "t": time.time(), "kind": kind, **fields}
    _log[run_id].append(event)
    if _loop is None:
        return
    for q in list(_subs[run_id]):
        _loop.call_soon_threadsafe(_put, q, event)


def _put(q: asyncio.Queue, event: dict) -> None:
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        pass


def history(run_id: str, after: int = 0) -> list[dict]:
    return [e for e in _log[run_id] if e["seq"] > after]


def subscribe(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=2000)
    _subs[run_id].add(q)
    return q


def unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    _subs[run_id].discard(q)


def sse(event: dict) -> str:
    return f"id: {event['seq']}\ndata: {json.dumps(event)}\n\n"
