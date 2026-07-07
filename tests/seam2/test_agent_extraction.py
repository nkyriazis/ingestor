from __future__ import annotations

import os

import pytest

from ingestor.agent import Agent
from ingestor.canonicalization import canonicalization_tool_spec
from ingestor.evidence import EvidenceNode
from ingestor.extract import EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt
from ingestor.llm import LlamaCppClient
from tests.fakes import FakeGraphClient, fake_mcp_tool_specs

pytestmark = [pytest.mark.seam2, pytest.mark.asyncio]

LLAMACPP_BASE_URL = os.environ.get("LLAMACPP_BASE_URL", "http://localhost:8080/v1")
LLAMACPP_MODEL = os.environ.get("LLAMACPP_MODEL", "Qwen3.6-27B-Q4_K_M.gguf")


def _agent(graph: FakeGraphClient) -> Agent:
    llm = LlamaCppClient(base_url=LLAMACPP_BASE_URL, model=LLAMACPP_MODEL)
    tools = [canonicalization_tool_spec(graph), *fake_mcp_tool_specs(graph)]
    return Agent(llm, tools=tools, max_turns=12)


async def test_extracts_a_person_and_links_a_mention_to_the_evidence() -> None:
    graph = FakeGraphClient()
    node = EvidenceNode(
        id="gmail:test-1",
        kind="email",
        source_ref="test-1",
        text=(
            "Hi team, Nikos Papadopoulos will lead the Q3 migration project "
            "starting Monday."
        ),
    )

    await _agent(graph).run(EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt(node))

    assert graph.write_calls, "expected the Agent to write at least one node"
    written = " ".join(f"{c.query} {c.params}" for c in graph.write_calls).lower()
    assert "papadopoulos" in written or "nikos" in written
    assert "mention" in written
    assert node.id.lower() in written, "Mention should link ABOUT the given Evidence id"


async def test_checks_canonicalization_candidates_before_minting_a_similar_name() -> None:
    graph = FakeGraphClient(existing_by_type={"Person": [("person-nick", "Nick")]})
    node = EvidenceNode(
        id="gmail:test-2",
        kind="email",
        source_ref="test-2",
        text="Quick note: Nikos approved the budget for the new server rack.",
    )

    await _agent(graph).run(EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt(node))

    assert graph.read_calls, "expected the Agent to check for existing similar entities"
    checked_names = [c.params.get("type") for c in graph.read_calls]
    assert "Person" in checked_names


async def test_thin_content_produces_no_writes() -> None:
    graph = FakeGraphClient()
    node = EvidenceNode(id="gmail:test-3", kind="email", source_ref="test-3", text="ok thanks")

    await _agent(graph).run(EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt(node))

    assert graph.write_calls == []


async def test_extraction_from_a_converted_attachment_mentions_the_attachments_own_evidence_id() -> (
    None
):
    graph = FakeGraphClient()
    attachment = EvidenceNode(
        id="gmail:test-4:attachment:0",
        kind="attachment",
        source_ref="notes.docx",
        filename="notes.docx",
        text="Maria Ionescu will own the vendor contract renewal.",
    )

    await _agent(graph).run(EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt(attachment))

    written = " ".join(f"{c.query} {c.params}" for c in graph.write_calls).lower()
    assert "maria" in written or "ionescu" in written
    assert attachment.id.lower() in written
