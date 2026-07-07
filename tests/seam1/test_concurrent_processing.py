from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from ingestor.convert import ConvertStep
from ingestor.evidence import EvidenceNode
from ingestor.events import Event, EventBus
from ingestor.extract import ExtractStep
from ingestor.pipeline import Pipeline, PipelineContext
from ingestor.progress import InMemoryProgressStore
from tests.fakes import FakeAgent, FakeGraphClient

pytestmark = [pytest.mark.seam1, pytest.mark.asyncio]


async def _drain(subscription: AsyncIterator[Event]) -> list[Event]:
    events = []
    while True:
        try:
            events.append(await asyncio.wait_for(anext(subscription), timeout=0.01))
        except TimeoutError:
            return events


async def test_two_independent_items_process_concurrently_not_sequentially() -> None:
    graph = FakeGraphClient()
    bus = EventBus()
    subscription = bus.subscribe()
    # A delay forces real overlap to be observable — without it, two fast
    # items could complete sequentially so quickly that "concurrent" and
    # "one after another" would be indistinguishable from the event order.
    slow_agent = FakeAgent(delay=0.05)
    ctx = PipelineContext(graph=graph, llm=None, agent=slow_agent)  # type: ignore[arg-type]
    pipeline = Pipeline([ConvertStep(), ExtractStep()], InMemoryProgressStore(), events=bus)
    node_a = EvidenceNode(id="item-a", kind="email", source_ref="a", text="hello a")
    node_b = EvidenceNode(id="item-b", kind="email", source_ref="b", text="hello b")

    await asyncio.gather(pipeline.process(node_a, ctx), pipeline.process(node_b, ctx))

    events = await _drain(subscription)
    extract_events = [e for e in events if e.data.get("step") == "extract"]
    first_completed_at = next(
        i for i, e in enumerate(extract_events) if e.kind == "step_completed"
    )
    started_before_first_completion = {
        e.data["item_id"]
        for e in extract_events[: first_completed_at + 1]
        if e.kind == "step_started"
    }
    assert started_before_first_completion == {"item-a", "item-b"}, (
        "both items' Extract should have started before either finished"
    )


async def test_a_failing_item_does_not_prevent_another_from_completing() -> None:
    graph = FakeGraphClient()
    failing_agent = FakeAgent(fail_times=1)
    ctx = PipelineContext(graph=graph, llm=None, agent=failing_agent)  # type: ignore[arg-type]
    pipeline = Pipeline([ConvertStep(), ExtractStep()], InMemoryProgressStore())
    node_a = EvidenceNode(id="item-a", kind="email", source_ref="a", text="hello a")
    node_b = EvidenceNode(id="item-b", kind="email", source_ref="b", text="hello b")

    results = await asyncio.gather(
        pipeline.process(node_a, ctx), pipeline.process(node_b, ctx), return_exceptions=True
    )

    assert sum(isinstance(r, RuntimeError) for r in results) == 1
    assert sum(r is None for r in results) == 1
