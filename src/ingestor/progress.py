from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class ProgressStore(Protocol):
    """Tracks which Steps have completed for a given item, internally to the
    ingestor (not inferred from graph state) — see ADR-backed decision in
    CONTEXT.md's Pipeline entry: a failure must resume at the last completed
    Step even if the failure was the graph write itself.
    """

    def completed_steps(self, item_id: str) -> set[str]: ...

    def mark_completed(self, item_id: str, step_name: str) -> None: ...


class InMemoryProgressStore:
    def __init__(self) -> None:
        self._data: dict[str, set[str]] = {}

    def completed_steps(self, item_id: str) -> set[str]:
        return set(self._data.get(item_id, set()))

    def mark_completed(self, item_id: str, step_name: str) -> None:
        self._data.setdefault(item_id, set()).add(step_name)


class JsonFileProgressStore:
    """Real implementation: a flat JSON file mapping item_id -> [step_name, ...]."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def completed_steps(self, item_id: str) -> set[str]:
        return set(self._read().get(item_id, []))

    def mark_completed(self, item_id: str, step_name: str) -> None:
        data = self._read()
        steps = set(data.get(item_id, []))
        steps.add(step_name)
        data[item_id] = sorted(steps)
        self._path.write_text(json.dumps(data))

    def _read(self) -> dict[str, list[str]]:
        if not self._path.exists():
            return {}
        return dict(json.loads(self._path.read_text()))
