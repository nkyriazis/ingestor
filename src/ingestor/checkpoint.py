from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class CheckpointStore(Protocol):
    """Each Connector's own internal bookkeeping (e.g. "newest Gmail message
    ID seen"). Deliberately not the graph: this must stay reliable
    independent of the graph MCP's availability (see CONTEXT.md's Connector
    entry).
    """

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value


class JsonFileCheckpointStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def get(self, key: str) -> str | None:
        return self._read().get(key)

    def set(self, key: str, value: str) -> None:
        data = self._read()
        data[key] = value
        self._path.write_text(json.dumps(data))

    def _read(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        return dict(json.loads(self._path.read_text()))
