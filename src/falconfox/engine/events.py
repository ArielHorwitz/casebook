"""A tiny asyncio pub/sub bus.

The engine publishes events (plain dicts); each subscriber (e.g. a connected
browser) gets its own unbounded queue. Publishing never blocks the engine on a
slow consumer. Events are the *only* way state leaves the engine, which keeps the
UI a pure reflection of engine state.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    @property
    def subscribers(self) -> int:
        """How many clients are listening. Zero means an event goes nowhere,
        which is worth knowing before waiting on one to answer."""
        return len(self._subscribers)

    def publish(self, event: dict) -> None:
        for queue in self._subscribers:
            queue.put_nowait(event)

    @contextmanager
    def subscribe(self):
        """Yield a queue receiving every event published while subscribed."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)
