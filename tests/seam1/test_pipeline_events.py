from __future__ import annotations

import pytest

from ingestor.evidence import EvidenceNode
from ingestor.events import Event, EventBus
from ingestor.pipeline import STEP_COMPLETED, STEP_FAILED, STEP_STARTED, Pipeline, PipelineContext
from ingestor.progress import InMemoryProgressStore

pytestmark = [pytest.mark.seam1, pytest.mark.asyncio]

DUMMY_CTX = PipelineContext(graph=None, llm=None, agent=None)  # type: ignore[arg-type]


class RecordingStep:
    def __init__(self, name: str, fail: bool = False) -> None:
        self.name = name
        self._fail = fail

    async def run(self, node: EvidenceNode, ctx: PipelineContext) -> None:
        if self._fail:
            raise RuntimeError("boom")


async def test_publishes_started_then_completed_for_a_successful_step() -> None:
    bus = EventBus()
    subscription = bus.subscribe()
    pipeline = Pipeline([RecordingStep("a")], InMemoryProgressStore(), events=bus)
    node = EvidenceNode(id="item-1", kind="email", source_ref="item-1")

    await pipeline.process(node, DUMMY_CTX)

    first = await anext(subscription)
    second = await anext(subscription)
    assert first == Event(STEP_STARTED, {"item_id": "item-1", "step": "a"})
    assert second == Event(STEP_COMPLETED, {"item_id": "item-1", "step": "a"})


async def test_publishes_failed_with_the_error_and_reraises() -> None:
    bus = EventBus()
    subscription = bus.subscribe()
    pipeline = Pipeline([RecordingStep("a", fail=True)], InMemoryProgressStore(), events=bus)
    node = EvidenceNode(id="item-1", kind="email", source_ref="item-1")

    with pytest.raises(RuntimeError):
        await pipeline.process(node, DUMMY_CTX)

    first = await anext(subscription)
    second = await anext(subscription)
    assert first.kind == STEP_STARTED
    assert second == Event(STEP_FAILED, {"item_id": "item-1", "step": "a", "error": "boom"})


async def test_a_skipped_already_completed_step_publishes_nothing() -> None:
    bus = EventBus()
    subscription = bus.subscribe()
    progress = InMemoryProgressStore()
    progress.mark_completed("item-1", "a")
    pipeline = Pipeline([RecordingStep("a")], progress, events=bus)
    node = EvidenceNode(id="item-1", kind="email", source_ref="item-1")

    await pipeline.process(node, DUMMY_CTX)
    bus.publish("sentinel")

    sentinel = await anext(subscription)
    assert sentinel.kind == "sentinel", "no step events should have preceded the sentinel"


async def test_behaves_identically_with_no_event_bus_supplied() -> None:
    pipeline = Pipeline([RecordingStep("a")], InMemoryProgressStore())
    node = EvidenceNode(id="item-1", kind="email", source_ref="item-1")

    await pipeline.process(node, DUMMY_CTX)  # must not raise
