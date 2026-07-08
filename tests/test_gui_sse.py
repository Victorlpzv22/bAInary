"""SSE broker test — small unit test for publish/subscribe, no HTTP."""

from __future__ import annotations

import asyncio
from typing import Any

from bainary.gui.sse import SSEBroker


def _run(coro):
    return asyncio.run(coro)


def test_subscribe_yields_events() -> None:
    async def go() -> None:
        broker = SSEBroker()
        async with broker.subscribe() as q:
            broker.publish("hello", {"x": 1})
            evt = await asyncio.wait_for(q.get(), timeout=1)
            assert evt["event"] == "hello"
            assert evt["data"] == {"x": 1}

    _run(go())


def test_multiple_subscribers_all_receive() -> None:
    async def go() -> None:
        broker = SSEBroker()
        async with broker.subscribe() as q1, broker.subscribe() as q2:
            broker.publish("x", {"v": 1})
            for q in (q1, q2):
                evt = await asyncio.wait_for(q.get(), timeout=1)
                assert evt["event"] == "x"
                assert evt["data"] == {"v": 1}

    _run(go())


def test_subscribe_after_publish_does_not_backfill() -> None:
    async def go() -> None:
        broker = SSEBroker()
        broker.publish("x", {"v": 1})
        async with broker.subscribe() as q:
            # No item arrives within 50ms (broadcasts are not buffered).
            try:
                evt = await asyncio.wait_for(q.get(), timeout=0.05)
            except TimeoutError:
                evt = None
            assert evt is None

    _run(go())


def test_subscribe_context_manager_unregisters() -> None:
    async def go() -> None:
        broker = SSEBroker()
        async with broker.subscribe():
            assert len(broker._subscribers) == 1
        assert len(broker._subscribers) == 0
        # Posting afterwards must not raise.
        broker.publish("after", {})

    _run(go())


def test_publish_with_non_str_keys_still_works() -> None:
    async def go() -> None:
        broker: SSEBroker = SSEBroker()
        async with broker.subscribe() as q:
            broker.publish("e", {"k": [1, 2, 3]})
            evt: dict[str, Any] = await asyncio.wait_for(q.get(), timeout=1)
            assert evt["data"]["k"] == [1, 2, 3]

    _run(go())


def test_publish_with_no_subscribers_does_not_raise() -> None:
    broker = SSEBroker()
    broker.publish("nobody", {"x": 1})  # must not raise
    assert broker._subscribers == []
