from __future__ import annotations

import pytest

from ingestor.evidence import EvidenceNode
from ingestor.pipeline import Pipeline, PipelineContext
from ingestor.progress import InMemoryProgressStore

pytestmark = [pytest.mark.seam1, pytest.mark.asyncio]

# Steps don't touch ctx in these tests, so a bare context with no real
# GraphClient/Agent is fine — Pipeline itself has no awareness of either.
DUMMY_CTX = PipelineContext(graph=None, llm=None, agent=None)  # type: ignore[arg-type]


class RecordingStep:
    def __init__(self, name: str, calls: list[str], fail_times: int = 0) -> None:
        self.name = name
        self._calls = calls
        self._fail_times = fail_times

    async def run(self, node: EvidenceNode, ctx: PipelineContext) -> None:
        self._calls.append(self.name)
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError(f"{self.name} failed")


def _node(item_id: str = "item-1") -> EvidenceNode:
    return EvidenceNode(id=item_id, kind="email", source_ref=item_id)


async def test_steps_run_in_order() -> None:
    calls: list[str] = []
    pipeline = Pipeline(
        [RecordingStep("a", calls), RecordingStep("b", calls)], InMemoryProgressStore()
    )

    await pipeline.process(_node(), DUMMY_CTX)

    assert calls == ["a", "b"]


async def test_a_failure_leaves_prior_steps_marked_complete_and_reraises() -> None:
    calls: list[str] = []
    progress = InMemoryProgressStore()
    node = _node()
    pipeline = Pipeline(
        [RecordingStep("a", calls), RecordingStep("b", calls, fail_times=1)], progress
    )

    with pytest.raises(RuntimeError, match="b failed"):
        await pipeline.process(node, DUMMY_CTX)

    assert calls == ["a", "b"]
    assert progress.completed_steps(node.id) == {"a"}


async def test_retry_resumes_at_the_last_completed_step() -> None:
    calls: list[str] = []
    progress = InMemoryProgressStore()
    node = _node()
    failing_b = RecordingStep("b", calls, fail_times=1)
    pipeline = Pipeline([RecordingStep("a", calls), failing_b], progress)

    with pytest.raises(RuntimeError):
        await pipeline.process(node, DUMMY_CTX)
    calls.clear()

    await pipeline.process(node, DUMMY_CTX)

    assert calls == ["b"]
    assert progress.completed_steps(node.id) == {"a", "b"}


async def test_a_second_item_tracks_progress_independently() -> None:
    calls: list[str] = []
    progress = InMemoryProgressStore()
    step = RecordingStep("a", calls)
    pipeline = Pipeline([step], progress)

    await pipeline.process(_node("item-1"), DUMMY_CTX)
    await pipeline.process(_node("item-2"), DUMMY_CTX)

    assert calls == ["a", "a"]
    assert progress.completed_steps("item-1") == {"a"}
    assert progress.completed_steps("item-2") == {"a"}
