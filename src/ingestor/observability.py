from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from sse_starlette.sse import EventSourceResponse
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route

from ingestor.events import EventBus

# No auth: bound to loopback/the compose network only, by design — this is
# a personal, single-user, local-only system (same reasoning as ADR 0002).
# Event payloads may include snippets of real email/note content, so this
# is a deliberate scope limit for now, not an oversight.


def create_app(bus: EventBus) -> Starlette:
    async def stream_events(request: Request) -> EventSourceResponse:
        async def event_generator() -> AsyncIterator[dict[str, Any]]:
            async for event in bus.subscribe():
                if await request.is_disconnected():
                    break
                yield {"event": event.kind, "data": json.dumps(event.data)}

        return EventSourceResponse(event_generator())

    return Starlette(routes=[Route("/events", stream_events)])
