from __future__ import annotations

from typing import Protocol


class Importer(Protocol):
    """Fetches from one external API (Gmail, Keep, Drive, etc.) and
    materializes new content into the shared filesystem Sink. Has no
    tree-building responsibility at all — that's the one FilesystemConnector's
    job, shared across every Importer (see ADR 0003 and CONTEXT.md's Importer
    entry).
    """

    def pull(self) -> None: ...
