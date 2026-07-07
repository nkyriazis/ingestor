from __future__ import annotations

import os

import pytest

from ingestor.convert import EvidenceWriter
from ingestor.evidence import EvidenceNode
from ingestor.mcp_tools import McpGraphClient, connect_mcp

pytestmark = [pytest.mark.seam3, pytest.mark.asyncio]

GRAPH_MCP_URL = os.environ.get("GRAPH_MCP_URL", "http://localhost:8000/mcp/")


async def test_write_then_read_round_trips_through_the_real_backend() -> None:
    async with connect_mcp(GRAPH_MCP_URL) as session:
        graph = McpGraphClient(session)
        try:
            await graph.write_cypher(
                "MERGE (t:Evidence {id: $id}) SET t.text = $text",
                {"id": "seam3:contract-1", "text": "hello"},
            )

            rows = await graph.read_cypher(
                "MATCH (t:Evidence {id: $id}) RETURN t.text AS text",
                {"id": "seam3:contract-1"},
            )

            assert rows == [{"text": "hello"}]
        finally:
            await graph.write_cypher("MATCH (n) WHERE n.id STARTS WITH 'seam3:' DETACH DELETE n")


async def test_evidence_tree_persists_contained_in_edges_with_position() -> None:
    async with connect_mcp(GRAPH_MCP_URL) as session:
        graph = McpGraphClient(session)
        try:
            tree = EvidenceNode(
                id="seam3:root",
                kind="email",
                source_ref="root",
                text="hi",
                children=[
                    EvidenceNode(id="seam3:child-0", kind="attachment", source_ref="a0", text="x"),
                    EvidenceNode(id="seam3:child-1", kind="attachment", source_ref="a1", text="y"),
                ],
            )

            await EvidenceWriter(graph).write(tree)

            rows = await graph.read_cypher(
                """
                MATCH (c:Evidence)-[r:CONTAINED_IN]->(:Evidence {id: $root})
                RETURN c.id AS id, r.position AS position
                ORDER BY r.position
                """,
                {"root": "seam3:root"},
            )

            assert rows == [
                {"id": "seam3:child-0", "position": 0},
                {"id": "seam3:child-1", "position": 1},
            ]
        finally:
            await graph.write_cypher("MATCH (n) WHERE n.id STARTS WITH 'seam3:' DETACH DELETE n")


async def test_re_writing_the_same_tree_does_not_duplicate_nodes() -> None:
    async with connect_mcp(GRAPH_MCP_URL) as session:
        graph = McpGraphClient(session)
        try:
            node = EvidenceNode(id="seam3:idempotent", kind="email", source_ref="e1", text="v1")

            await EvidenceWriter(graph).write(node)
            node.text = "v2"
            await EvidenceWriter(graph).write(node)

            rows = await graph.read_cypher(
                "MATCH (e:Evidence {id: $id}) RETURN e.text AS text", {"id": "seam3:idempotent"}
            )

            assert rows == [{"text": "v2"}]
        finally:
            await graph.write_cypher("MATCH (n) WHERE n.id STARTS WITH 'seam3:' DETACH DELETE n")
