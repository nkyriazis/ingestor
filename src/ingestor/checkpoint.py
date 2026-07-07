from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ingestor import _jsonfile


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
        value = _jsonfile.read(self._path).get(key)
        return str(value) if value is not None else None

    def set(self, key: str, value: str) -> None:
        data = _jsonfile.read(self._path)
        data[key] = value
        _jsonfile.write(self._path, data)
