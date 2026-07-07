from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ingestor.agent import Agent
from ingestor.evidence import EvidenceNode
from ingestor.events import EventBus, default_events
from ingestor.graph import GraphClient
from ingestor.llm import LlamaCppClient
from ingestor.progress import ProgressStore

STEP_STARTED = "step_started"
STEP_COMPLETED = "step_completed"
STEP_FAILED = "step_failed"


@dataclass
class PipelineContext:
    """Shared dependencies every Step may need. Plain data — the Pipeline
    itself has no awareness of what's inside (see CONTEXT.md's Pipeline
    entry: no awareness of LLMs, only specific Steps happen to call one).

    `llm` is the bare model client, for narrow one-shot calls that need no
    tools (e.g. image captioning); `agent` wraps it with tool-calling for
    judgment-requiring, graph-writing work (extraction, canonicalization).
    """

    graph: GraphClient
    llm: LlamaCppClient
    agent: Agent


class Step(Protocol):
    name: str

    async def run(self, node: EvidenceNode, ctx: PipelineContext) -> None: ...


class Pipeline:
    """Runs each Evidence item through an ordered sequence of Steps, tracking
    per-item progress so a failure resumes at the last completed Step
    instead of restarting. Publishes Step lifecycle events to `events` (a
    fresh, subscriber-less EventBus by default — a safe no-op) so observers
    can see what's happening without the Pipeline itself needing to know
    whether anyone's watching.
    """

    def __init__(
        self, steps: list[Step], progress: ProgressStore, events: EventBus | None = None
    ) -> None:
        self._steps = steps
        self._progress = progress
        self._events = default_events(events)

    async def process(self, node: EvidenceNode, ctx: PipelineContext) -> None:
        done = self._progress.completed_steps(node.id)
        for step in self._steps:
            if step.name in done:
                continue
            self._events.publish(STEP_STARTED, item_id=node.id, step=step.name)
            try:
                await step.run(node, ctx)
            except Exception as error:
                self._events.publish(
                    STEP_FAILED, item_id=node.id, step=step.name, error=str(error)
                )
                raise
            self._progress.mark_completed(node.id, step.name)
            self._events.publish(STEP_COMPLETED, item_id=node.id, step=step.name)
