from __future__ import annotations

import os

import pytest

from ingestor.convert import EvidenceWriter
from ingestor.evidence import EvidenceNode
from ingestor.mcp_tools import McpGraphClient, connect_mcp

pytestmark = [pytest.mark.seam3, pytest.mark.asyncio]

GRAPH_MCP_URL = os.environ.get("GRAPH_MCP_URL", "http://localhost:8000/mcp/")


async def _cleanup(graph: McpGraphClient) -> None:
    await graph.write_cypher("MATCH (n) WHERE n.id STARTS WITH 'seam3:' DETACH DELETE n")


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
            await _cleanup(graph)


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
            await _cleanup(graph)


async def test_a_specific_nested_image_is_directly_addressable_by_position() -> None:
    """The 1st image of the 2nd file of an email — the exact query pattern
    that motivated per-node Evidence and ordinal CONTAINED_IN positions.
    """
    async with connect_mcp(GRAPH_MCP_URL) as session:
        graph = McpGraphClient(session)
        try:
            tree = EvidenceNode(
                id="seam3:email",
                kind="email",
                source_ref="email",
                text="see attached",
                children=[
                    EvidenceNode(id="seam3:file-0", kind="attachment", source_ref="f0", text="x"),
                    EvidenceNode(
                        id="seam3:file-1",
                        kind="attachment",
                        source_ref="f1",
                        children=[
                            EvidenceNode(
                                id="seam3:file-1:image-0", kind="image", source_ref="i0", text="a"
                            ),
                            EvidenceNode(
                                id="seam3:file-1:image-1", kind="image", source_ref="i1", text="b"
                            ),
                        ],
                    ),
                ],
            )

            await EvidenceWriter(graph).write(tree)

            rows = await graph.read_cypher(
                """
                MATCH (email:Evidence {id: $email})<-[:CONTAINED_IN {position: 1}]-(file:Evidence)
                MATCH (file)<-[:CONTAINED_IN {position: 0}]-(image:Evidence)
                RETURN image.id AS id, image.text AS text
                """,
                {"email": "seam3:email"},
            )

            assert rows == [{"id": "seam3:file-1:image-0", "text": "a"}]
        finally:
            await _cleanup(graph)


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
            await _cleanup(graph)
