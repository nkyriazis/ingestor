from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

from ingestor.tools import ToolSpec


@asynccontextmanager
async def connect_mcp(url: str) -> AsyncIterator[ClientSession]:
    """Connects to the configured graph MCP (see CONTEXT.md's Connector/Agent
    entries — the ingestor doesn't control this surface, only what it does
    with it).
    """
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _text_of(result: Any) -> str:
    return "\n".join(part.text for part in result.content if isinstance(part, TextContent))


class McpGraphClient:
    """Deterministic GraphClient backed by a real graph MCP session, called
    directly by our own code (not via an LLM tool-calling loop) — used for
    mechanical writes like the Evidence tree, which need no judgment.
    """

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def read_cypher(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        result = await self._session.call_tool(
            "read_neo4j_cypher", {"query": query, "params": params or {}}
        )
        return _parse_rows(_text_of(result))

    async def write_cypher(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        result = await self._session.call_tool(
            "write_neo4j_cypher", {"query": query, "params": params or {}}
        )
        return _parse_rows(_text_of(result))


def _parse_rows(text: str) -> list[dict[str, Any]]:
    if not text:
        return []
    parsed = json.loads(text)
    return list(parsed) if isinstance(parsed, list) else [parsed]


async def mcp_agent_tools(session: ClientSession, read_only: bool = False) -> list[ToolSpec]:
    """Wraps tools the connected MCP exposes as Agent ToolSpecs, so the
    Agent's LLM can call them directly during its reasoning loop.

    `read_only=True` keeps only tools the MCP itself annotates with
    `readOnlyHint: true` (e.g. `read_neo4j_cypher`, `get_neo4j_schema`, not
    `write_neo4j_cypher`) — for a query Agent, which should never write.
    A tool with no annotations at all is excluded when `read_only=True`,
    since we can't confirm it's safe.
    """
    listed = await session.list_tools()
    tools = listed.tools
    if read_only:
        tools = [tool for tool in tools if tool.annotations and tool.annotations.readOnlyHint]
    return [
        ToolSpec(
            name=tool.name,
            description=tool.description or "",
            input_schema=tool.inputSchema,
            handler=_make_handler(session, tool.name),
        )
        for tool in tools
    ]


def _make_handler(session: ClientSession, name: str) -> Any:
    async def handler(arguments: dict[str, Any]) -> str:
        result = await session.call_tool(name, arguments)
        return _text_of(result)

    return handler
