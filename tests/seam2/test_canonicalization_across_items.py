from __future__ import annotations

import os

import pytest

from ingestor.agent import Agent
from ingestor.canonicalization import canonicalization_tool_spec
from ingestor.evidence import EvidenceNode
from ingestor.extract import EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt
from ingestor.llm import LlamaCppClient
from ingestor.mcp_tools import McpGraphClient, connect_mcp, mcp_agent_tools
from ingestor.tools import ToolSpec

pytestmark = [pytest.mark.seam2, pytest.mark.asyncio]

LLAMACPP_BASE_URL = os.environ.get("LLAMACPP_BASE_URL", "http://localhost:8080/v1")
LLAMACPP_MODEL = os.environ.get("LLAMACPP_MODEL", "Qwen3.6-27B-Q4_K_M.gguf")
GRAPH_MCP_URL = os.environ.get("GRAPH_MCP_URL", "http://localhost:8000/mcp/")

# A synthetic, made-up surname so this test can never collide with real data
# and can clean up precisely by name.
SURNAME = "Vorlonquist"


async def _extract(graph: McpGraphClient, tools: list[ToolSpec], node: EvidenceNode) -> None:
    await Agent(LlamaCppClient(base_url=LLAMACPP_BASE_URL, model=LLAMACPP_MODEL), tools=tools, max_turns=12).run(
        EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt(node)
    )


async def _cleanup(graph: McpGraphClient) -> None:
    await graph.write_cypher(
        "MATCH (m:Mention)-[:ABOUT]->(e:Evidence) "
        "WHERE e.id STARTS WITH 'seam-canon:' DETACH DELETE m"
    )
    await graph.write_cypher("MATCH (e:Evidence) WHERE e.id STARTS WITH 'seam-canon:' DETACH DELETE e")
    await graph.write_cypher(
        "MATCH (k:Knowledge) WHERE k.name CONTAINS $surname DETACH DELETE k", {"surname": SURNAME}
    )


async def test_a_near_miss_name_in_a_second_item_reuses_the_first_items_person_node() -> None:
    async with connect_mcp(GRAPH_MCP_URL) as session:
        graph = McpGraphClient(session)
        tools = [canonicalization_tool_spec(graph), *await mcp_agent_tools(session)]
        try:
            await _extract(
                graph,
                tools,
                EvidenceNode(
                    id="seam-canon:e1",
                    kind="email",
                    source_ref="e1",
                    text=f"Nick {SURNAME} approved the Q3 budget for the new office.",
                ),
            )
            await _extract(
                graph,
                tools,
                EvidenceNode(
                    id="seam-canon:e2",
                    kind="email",
                    source_ref="e2",
                    text=f"Nikos {SURNAME} signed off on the server rack purchase order.",
                ),
            )

            rows = await graph.read_cypher(
                "MATCH (p:Knowledge {type: 'Person'}) WHERE p.name CONTAINS $surname "
                "RETURN p.id AS id, p.name AS name",
                {"surname": SURNAME},
            )

            assert len(rows) == 1, f"expected the second mention to reuse one Person node, got {rows}"
        finally:
            await _cleanup(graph)


async def test_an_unrelated_name_in_a_second_item_does_not_get_merged_into_the_first() -> None:
    async with connect_mcp(GRAPH_MCP_URL) as session:
        graph = McpGraphClient(session)
        tools = [canonicalization_tool_spec(graph), *await mcp_agent_tools(session)]
        try:
            await _extract(
                graph,
                tools,
                EvidenceNode(
                    id="seam-canon:e3",
                    kind="email",
                    source_ref="e3",
                    text=f"Nick {SURNAME} approved the Q3 budget for the new office.",
                ),
            )
            await _extract(
                graph,
                tools,
                EvidenceNode(
                    id="seam-canon:e4",
                    kind="email",
                    source_ref="e4",
                    text=f"Priya Chandrasekaran-{SURNAME} reviewed the vendor contract renewal.",
                ),
            )

            rows = await graph.read_cypher(
                "MATCH (p:Knowledge {type: 'Person'}) WHERE p.name CONTAINS $surname "
                "RETURN p.id AS id, p.name AS name",
                {"surname": SURNAME},
            )

            assert len(rows) == 2, (
                f"expected two distinct, unrelated Person nodes to remain separate, got {rows}"
            )
        finally:
            await _cleanup(graph)
