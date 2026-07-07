from __future__ import annotations

import pytest

from ingestor.convert import ConvertStep
from ingestor.evidence import EvidenceNode
from ingestor.extract import ExtractStep
from ingestor.pipeline import Pipeline, PipelineContext
from ingestor.progress import InMemoryProgressStore
from tests.fakes import FakeAgent, FakeGraphClient

pytestmark = [pytest.mark.seam1, pytest.mark.asyncio]


async def test_a_failure_in_extract_does_not_lose_converts_already_persisted_output() -> None:
    graph = FakeGraphClient()
    agent = FakeAgent(fail_times=1)
    progress = InMemoryProgressStore()
    ctx = PipelineContext(graph=graph, llm=None, agent=agent)  # type: ignore[arg-type]
    node = EvidenceNode(id="gmail:e1", kind="email", source_ref="e1", text="Nikos owns the rollout.")
    pipeline = Pipeline([ConvertStep(), ExtractStep()], progress)

    with pytest.raises(RuntimeError, match="simulated Agent failure"):
        await pipeline.process(node, ctx)

    assert progress.completed_steps(node.id) == {"convert"}
    assert graph.write_calls, "Convert's write should have persisted before Extract failed"
    assert len(agent.calls) == 1


async def test_retry_resumes_at_extract_without_re_running_convert() -> None:
    graph = FakeGraphClient()
    agent = FakeAgent(fail_times=1)
    progress = InMemoryProgressStore()
    ctx = PipelineContext(graph=graph, llm=None, agent=agent)  # type: ignore[arg-type]
    node = EvidenceNode(id="gmail:e2", kind="email", source_ref="e2", text="Nikos owns the rollout.")
    pipeline = Pipeline([ConvertStep(), ExtractStep()], progress)

    with pytest.raises(RuntimeError):
        await pipeline.process(node, ctx)
    writes_after_first_attempt = len(graph.write_calls)

    await pipeline.process(node, ctx)

    assert len(graph.write_calls) == writes_after_first_attempt, "Convert should not run again"
    assert len(agent.calls) == 2, "Extract should have been retried, not skipped"
    assert progress.completed_steps(node.id) == {"convert", "extract"}
