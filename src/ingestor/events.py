from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    kind: str
    data: dict[str, Any]


class EventBus:
    """Async-safe, in-process publish/subscribe for observing what the
    ingestor is doing (see CONTEXT.md's Event Bus entry). No persistence —
    a subscriber only ever sees events published while it's subscribed
    (live-tail), never a backlog.

    Safe under concurrent publishers and concurrent subscribers: asyncio is
    single-threaded and cooperative, so the subscriber list is never
    mutated and iterated in an interleaved way — `publish` iterates a
    snapshot of the list, and list append/remove are atomic between
    `await` points. A default (subscriber-less) instance is a no-op:
    `publish` with nothing to fan out to costs nothing.
    """

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[Event]] = []

    def publish(self, kind: str, **data: Any) -> None:
        event = Event(kind=kind, data=data)
        for queue in list(self._subscribers):
            queue.put_nowait(event)

    def subscribe(self) -> AsyncIterator[Event]:
        # Registering the queue happens here, synchronously, NOT inside the
        # generator below — an async generator's body doesn't run until
        # first iterated, so if registration lived there, an event
        # published between calling subscribe() and the first `async for`
        # would be silently missed.
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers.append(queue)
        return self._consume(queue)

    async def _consume(self, queue: asyncio.Queue[Event]) -> AsyncIterator[Event]:
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.remove(queue)
