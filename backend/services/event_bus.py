"""In-memory per-user event broker used to push notifications to connected
clients (web, desktop) via Server-Sent Events.

This is a single-process implementation — it does not fan out across
multiple uvicorn workers. We deploy with a single worker today, so that's
fine; if we scale horizontally later, swap this for Redis pub/sub with the
same public interface.
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Set
from uuid import UUID

from loguru import logger


# user_id (str) -> set of asyncio.Queue subscribed for that user.
_subscribers: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
_lock = asyncio.Lock()


def _user_key(user_id: UUID | str) -> str:
    return str(user_id)


async def publish(user_id: UUID | str, event: str, data: Any) -> None:
    """Fan out an event to every connected client of the given user.

    `event`  — short event name (e.g. "export_created")
    `data`   — JSON-serialisable payload
    """
    key = _user_key(user_id)
    payload = {"event": event, "data": data}
    async with _lock:
        queues = list(_subscribers.get(key, ()))
    if not queues:
        return
    for q in queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning(f"event_bus: dropping event for {key} — queue full")


@asynccontextmanager
async def subscribe(user_id: UUID | str) -> AsyncIterator[asyncio.Queue]:
    """Async context manager that yields a queue receiving events for the user."""
    key = _user_key(user_id)
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    async with _lock:
        _subscribers[key].add(q)
    try:
        yield q
    finally:
        async with _lock:
            _subscribers[key].discard(q)
            if not _subscribers[key]:
                _subscribers.pop(key, None)


async def sse_stream(user_id: UUID | str, heartbeat_seconds: float = 25.0) -> AsyncIterator[str]:
    """Yield SSE-formatted lines for the given user.

    Emits a comment-only heartbeat every `heartbeat_seconds` to keep the
    connection open through proxies (nginx default idle timeout = 60s).
    """
    async with subscribe(user_id) as q:
        # Initial ready event lets the client confirm subscription is active.
        yield _format_event("ready", {"user_id": str(user_id)})
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=heartbeat_seconds)
            except asyncio.TimeoutError:
                # Comment line — SSE spec: lines starting with ":" are ignored
                # by the client but keep the TCP/HTTP stream alive.
                yield ": ping\n\n"
                continue
            yield _format_event(payload["event"], payload["data"])


def _format_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
