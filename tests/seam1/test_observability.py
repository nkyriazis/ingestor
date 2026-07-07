from __future__ import annotations

import asyncio

import httpx
import pytest
import uvicorn

from ingestor.events import EventBus
from ingestor.observability import create_app

pytestmark = [pytest.mark.seam1, pytest.mark.asyncio]


async def test_published_events_arrive_as_sse_messages_in_order() -> None:
    # A real socket, not httpx.ASGITransport: ASGITransport awaits the whole
    # app call before returning a response, which never happens for a
    # deliberately open-ended SSE stream. A real server is what "verified
    # end-to-end against a running server" (the acceptance criterion)
    # actually means for an endpoint like this.
    bus = EventBus()
    app = create_app(bus)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.ensure_future(server.serve())
    try:
        while not server.started:
            await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            async with client.stream("GET", "/events") as response:
                assert response.status_code == 200

                async def publish_soon() -> None:
                    await asyncio.sleep(0.05)
                    bus.publish("first", n=1)
                    bus.publish("second", n=2)

                asyncio.ensure_future(publish_soon())

                received: list[str] = []
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        received.append(line.removeprefix("event:").strip())
                    if len(received) == 2:
                        break
    finally:
        server.should_exit = True
        await server_task

    assert received == ["first", "second"]
