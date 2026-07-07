from __future__ import annotations

import pytest

from ingestor.evidence import EvidenceNode
from ingestor.extract import ExtractStep
from ingestor.pipeline import PipelineContext
from tests.fakes import FakeAgent

pytestmark = [pytest.mark.seam1, pytest.mark.asyncio]


async def test_runs_the_agent_once_per_node_with_text_in_the_tree() -> None:
    agent = FakeAgent()
    ctx = PipelineContext(graph=None, llm=None, agent=agent)  # type: ignore[arg-type]
    email = EvidenceNode(
        id="gmail:e1",
        kind="email",
        source_ref="e1",
        text="see attached",
        children=[
            EvidenceNode(id="gmail:e1:attachment:0", kind="attachment", source_ref="a0", text="a"),
            EvidenceNode(id="gmail:e1:attachment:1", kind="attachment", source_ref="a1", text=None),
        ],
    )

    await ExtractStep().run(email, ctx)

    prompts = [user_prompt for _, user_prompt in agent.calls]
    assert any("gmail:e1\n" in p for p in prompts)
    assert any("gmail:e1:attachment:0" in p for p in prompts)
    assert not any("gmail:e1:attachment:1" in p for p in prompts)
    assert len(agent.calls) == 2


async def test_a_node_with_no_text_anywhere_in_the_tree_never_calls_the_agent() -> None:
    agent = FakeAgent()
    ctx = PipelineContext(graph=None, llm=None, agent=agent)  # type: ignore[arg-type]
    node = EvidenceNode(id="gmail:e2", kind="email", source_ref="e2", text=None)

    await ExtractStep().run(node, ctx)

    assert agent.calls == []
