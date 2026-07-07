from __future__ import annotations

import os

import pytest

from ingestor.agent import AGENT_FINISHED, TOOL_CALLED, Agent
from ingestor.canonicalization import canonicalization_tool_spec
from ingestor.evidence import EvidenceNode
from ingestor.events import EventBus
from ingestor.extract import EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt
from ingestor.llm import LlamaCppClient
from tests.fakes import FakeGraphClient, fake_mcp_tool_specs

pytestmark = [pytest.mark.seam2, pytest.mark.asyncio]

LLAMACPP_BASE_URL = os.environ.get("LLAMACPP_BASE_URL", "http://localhost:8080/v1")
LLAMACPP_MODEL = os.environ.get("LLAMACPP_MODEL", "Qwen3.6-27B-Q4_K_M.gguf")


async def test_a_real_extraction_run_publishes_tool_called_then_agent_finished() -> None:
    graph = FakeGraphClient()
    bus = EventBus()
    subscription = bus.subscribe()
    llm = LlamaCppClient(base_url=LLAMACPP_BASE_URL, model=LLAMACPP_MODEL)
    tools = [canonicalization_tool_spec(graph), *fake_mcp_tool_specs(graph)]
    agent = Agent(llm, tools=tools, max_turns=12, events=bus)
    node = EvidenceNode(
        id="gmail:test-events",
        kind="email",
        source_ref="test-events",
        text="Elena Marchetti will own the Q4 marketing campaign.",
    )

    summary = await agent.run(EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt(node))

    events = []
    while True:
        event = await anext(subscription)
        events.append(event)
        if event.kind == AGENT_FINISHED:
            break

    assert events[-1].kind == AGENT_FINISHED
    assert events[-1].data == {"summary": summary}
    tool_calls = [event for event in events if event.kind == TOOL_CALLED]
    assert tool_calls, "expected at least one tool_called event before agent_finished"
    assert all("name" in event.data and "arguments" in event.data for event in tool_calls)
