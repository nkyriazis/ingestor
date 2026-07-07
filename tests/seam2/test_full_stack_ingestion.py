from __future__ import annotations

import os
from pathlib import Path

import pytest

from ingestor.agent import Agent
from ingestor.canonicalization import canonicalization_tool_spec
from ingestor.checkpoint import InMemoryCheckpointStore
from ingestor.connectors.filesystem import FilesystemConnector
from ingestor.convert import ConvertStep
from ingestor.extract import ExtractStep
from ingestor.importers.gmail import GmailImporter, GmailMessage
from ingestor.llm import LlamaCppClient
from ingestor.mcp_tools import McpGraphClient, connect_mcp, mcp_agent_tools
from ingestor.pipeline import Pipeline, PipelineContext
from ingestor.progress import InMemoryProgressStore
from ingestor.query import QUERY_SYSTEM_PROMPT
from tests.fakes import FakeGmailClient

pytestmark = [pytest.mark.seam2, pytest.mark.asyncio]

LLAMACPP_BASE_URL = os.environ.get("LLAMACPP_BASE_URL", "http://localhost:8080/v1")
LLAMACPP_MODEL = os.environ.get("LLAMACPP_MODEL", "Qwen3.6-27B-Q4_K_M.gguf")
GRAPH_MCP_URL = os.environ.get("GRAPH_MCP_URL", "http://localhost:8000/mcp/")

# A synthetic surname so this test can never collide with real data and can
# clean up precisely by name.
SURNAME = "Featherstonehaugh"


async def test_a_fake_email_flows_through_the_real_stack_into_a_traceable_fact(
    tmp_path: Path,
) -> None:
    """Every piece is real except the OAuth-gated Gmail API itself, which
    nothing in an automated test can call anyway: real GmailImporter, real
    Sink, real FilesystemConnector, real Pipeline, real Agent against the
    running llama.cpp, real neo4j via neo4j-mcp.
    """
    async with connect_mcp(GRAPH_MCP_URL) as session:
        graph = McpGraphClient(session)
        try:
            llm = LlamaCppClient(base_url=LLAMACPP_BASE_URL, model=LLAMACPP_MODEL)
            tools = [canonicalization_tool_spec(graph), *await mcp_agent_tools(session)]
            agent = Agent(llm, tools=tools, max_turns=12)
            pipeline = Pipeline([ConvertStep(), ExtractStep()], InMemoryProgressStore())
            ctx = PipelineContext(graph=graph, llm=llm, agent=agent)

            gmail_client = FakeGmailClient(
                [
                    (
                        [
                            GmailMessage(
                                id="e2e-1",
                                body_text=f"Maria {SURNAME} will own the Q4 rollout.",
                            )
                        ],
                        "hist-1",
                    )
                ]
            )
            GmailImporter(gmail_client, InMemoryCheckpointStore(), tmp_path).pull()

            nodes = FilesystemConnector(tmp_path, InMemoryCheckpointStore()).poll()
            assert nodes, "the Connector should have discovered what the Importer wrote"

            for node in nodes:
                await pipeline.process(node, ctx)

            rows = await graph.read_cypher(
                """
                MATCH (k:Knowledge {type: 'Person'})<-[:TOUCHED]-(m:Mention)-[:ABOUT]->(e:Evidence)
                WHERE k.name CONTAINS $surname
                RETURN k.name AS name, e.id AS evidence_id, e.text AS evidence_text
                """,
                {"surname": SURNAME},
            )

            assert rows, "expected a Knowledge node traceable back to its Evidence"
            assert rows[0]["evidence_id"].startswith("gmail/e2e-1")
            assert SURNAME in (rows[0]["evidence_text"] or "")

            query_tools = [
                canonicalization_tool_spec(graph),
                *await mcp_agent_tools(session, read_only=True),
            ]
            query_agent = Agent(llm, tools=query_tools, max_turns=12)

            answer = await query_agent.run(
                QUERY_SYSTEM_PROMPT, "Who owns the Q4 rollout, and what's your source for that?"
            )

            assert SURNAME in answer, f"expected the answer to name the person, got: {answer!r}"
            assert "gmail/e2e-1" in answer, f"expected the answer to cite its Evidence id, got: {answer!r}"
        finally:
            await graph.write_cypher(
                "MATCH (m:Mention)-[:ABOUT]->(e:Evidence) "
                "WHERE e.id STARTS WITH 'gmail/e2e-1' DETACH DELETE m"
            )
            await graph.write_cypher(
                "MATCH (e:Evidence) WHERE e.id STARTS WITH 'gmail/e2e-1' DETACH DELETE e"
            )
            await graph.write_cypher(
                "MATCH (k:Knowledge) WHERE k.name CONTAINS $surname DETACH DELETE k",
                {"surname": SURNAME},
            )
