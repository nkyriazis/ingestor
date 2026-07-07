from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ingestor.agent import Agent
from ingestor.evidence import EvidenceNode
from ingestor.graph import GraphClient
from ingestor.progress import ProgressStore


@dataclass
class PipelineContext:
    """Shared dependencies every Step may need. Plain data — the Pipeline
    itself has no awareness of what's inside (see CONTEXT.md's Pipeline
    entry: no awareness of LLMs, only specific Steps happen to call one).
    """

    graph: GraphClient
    agent: Agent


class Step(Protocol):
    name: str

    async def run(self, node: EvidenceNode, ctx: PipelineContext) -> None: ...


class Pipeline:
    """Runs each Evidence item through an ordered sequence of Steps, tracking
    per-item progress so a failure resumes at the last completed Step
    instead of restarting.
    """

    def __init__(self, steps: list[Step], progress: ProgressStore) -> None:
        self._steps = steps
        self._progress = progress

    async def process(self, node: EvidenceNode, ctx: PipelineContext) -> None:
        done = self._progress.completed_steps(node.id)
        for step in self._steps:
            if step.name in done:
                continue
            await step.run(node, ctx)
            self._progress.mark_completed(node.id, step.name)
