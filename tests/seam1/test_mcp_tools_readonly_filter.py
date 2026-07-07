from __future__ import annotations

from dataclasses import dataclass

import pytest
from mcp.types import ListToolsResult, Tool, ToolAnnotations

from ingestor.mcp_tools import mcp_agent_tools

pytestmark = [pytest.mark.seam1, pytest.mark.asyncio]


def _tool(name: str, read_only: bool | None) -> Tool:
    return Tool(
        name=name,
        description=f"{name} tool",
        inputSchema={"type": "object", "properties": {}},
        annotations=ToolAnnotations(readOnlyHint=read_only) if read_only is not None else None,
    )


@dataclass
class FakeSession:
    tools: list[Tool]

    async def list_tools(self) -> ListToolsResult:
        return ListToolsResult(tools=self.tools)


async def test_read_only_false_keeps_every_tool() -> None:
    session = FakeSession(
        [_tool("read_neo4j_cypher", True), _tool("write_neo4j_cypher", False)]
    )

    tools = await mcp_agent_tools(session, read_only=False)  # type: ignore[arg-type]

    assert {t.name for t in tools} == {"read_neo4j_cypher", "write_neo4j_cypher"}


async def test_read_only_true_keeps_only_read_only_annotated_tools() -> None:
    session = FakeSession(
        [_tool("read_neo4j_cypher", True), _tool("write_neo4j_cypher", False)]
    )

    tools = await mcp_agent_tools(session, read_only=True)  # type: ignore[arg-type]

    assert {t.name for t in tools} == {"read_neo4j_cypher"}


async def test_read_only_true_excludes_a_tool_with_no_annotations_at_all() -> None:
    session = FakeSession([_tool("mystery_tool", None)])

    tools = await mcp_agent_tools(session, read_only=True)  # type: ignore[arg-type]

    assert tools == []
