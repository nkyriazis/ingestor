from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from ingestor.importers.gmail import GmailMessage
from ingestor.tools import ToolSpec


@dataclass
class FakeAgent:
    """Seam 1 stand-in for ingestor.agent.Agent, so Steps that invoke the
    Agent can be tested without any LLM involved. `fail_times` lets a test
    simulate a Step failing partway through, e.g. to exercise Pipeline
    resumability. `delay` lets a test force two concurrent Pipeline.process()
    calls to overlap, to exercise real concurrency rather than just asserting
    two coroutines were scheduled.
    """

    calls: list[tuple[str, str]] = field(default_factory=list)
    fail_times: int = 0
    delay: float = 0

    async def run(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("simulated Agent failure")
        return ""


class FakeGmailClient:
    """Seam 1 fake: replaces the real Gmail API with pre-scripted batches."""

    def __init__(self, batches: list[tuple[list[GmailMessage], str | None]]) -> None:
        self._batches = list(batches)
        self.checkpoints_requested: list[str | None] = []

    def list_new_messages(
        self, checkpoint: str | None
    ) -> tuple[list[GmailMessage], str | None]:
        self.checkpoints_requested.append(checkpoint)
        if not self._batches:
            return [], checkpoint
        return self._batches.pop(0)


@dataclass
class RecordedCall:
    query: str
    params: dict[str, Any]


@dataclass
class FakeGraphClient:
    """Seam 1/2 fake: an in-memory stand-in for the graph MCP. Doesn't
    interpret Cypher — just records calls and answers canonicalization
    lookups from a pre-seeded table, per the PRD's "fake/generic tool
    surface (not necessarily the real graph schema)" testing decision.
    """

    existing_by_type: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    write_calls: list[RecordedCall] = field(default_factory=list)
    read_calls: list[RecordedCall] = field(default_factory=list)

    async def read_cypher(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        params = params or {}
        self.read_calls.append(RecordedCall(query, params))
        existing = self.existing_by_type.get(params.get("type", ""), [])
        return [{"id": node_id, "name": name} for node_id, name in existing]

    async def write_cypher(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        params = params or {}
        self.write_calls.append(RecordedCall(query, params))
        return []


def fake_mcp_tool_specs(graph: FakeGraphClient) -> list[ToolSpec]:
    """Same tool names/shape the real neo4j MCP exposes, backed by a
    FakeGraphClient — lets Seam 2 tests exercise the Agent's real
    tool-calling behavior without a real graph backend.
    """

    async def read_handler(arguments: dict[str, Any]) -> str:
        rows = await graph.read_cypher(arguments["query"], arguments.get("params"))
        return json.dumps(rows)

    async def write_handler(arguments: dict[str, Any]) -> str:
        rows = await graph.write_cypher(arguments["query"], arguments.get("params"))
        return json.dumps(rows)

    cypher_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The Cypher query to execute."},
            "params": {"type": "object", "description": "Query parameters."},
        },
        "required": ["query"],
    }
    return [
        ToolSpec(
            name="read_neo4j_cypher",
            description="Execute a read Cypher query on the neo4j database.",
            input_schema=cypher_schema,
            handler=read_handler,
        ),
        ToolSpec(
            name="write_neo4j_cypher",
            description="Execute a write Cypher query on the neo4j database.",
            input_schema=cypher_schema,
            handler=write_handler,
        ),
    ]
