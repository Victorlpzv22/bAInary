"""Server-Sent Events broker for the bAInary GUI.

A small in-process pub/sub used by background jobs (lift, refine,
rag_build) to push progress events to every connected browser tab. Each
subscriber holds its own ``asyncio.Queue``; ``publish`` is non-blocking
and silently drops messages for slow consumers (queues have a bounded
size to avoid memory leaks).

The HTTP SSE endpoint is implemented in :mod:`bainary.gui.routes.refine`
(the only place that needs server-streaming today).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

_QUEUE_MAX = 256


class SSEBroker:
    """In-process pub/sub for SSE events.

    Each :meth:`subscribe` yields a fresh :class:`asyncio.Queue`. The
    context manager unregisters the queue on exit, so dropped clients
    are cleaned up automatically.
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        """Register a new queue; the context manager unregisters on exit."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_QUEUE_MAX)
        self._subscribers.append(q)
        try:
            yield q
        finally:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def publish(self, event: str, data: dict[str, Any]) -> None:
        """Push an event to every subscriber (best-effort, non-blocking).

        If a subscriber's queue is full, the event is dropped for that
        subscriber only — the next event will succeed once the consumer
        has drained.
        """
        payload = {"event": event, "data": data}
        for q in self._subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Drop on the floor; the consumer will catch up on the
                # next event. (We log nothing here: the typical cause is
                # a tab being throttled, not a server-side problem.)
                pass

    def subscriber_count(self) -> int:
        """Return the current number of subscribers (for diagnostics)."""
        return len(self._subscribers)
