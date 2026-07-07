from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ingestor.checkpoint import CheckpointStore
from ingestor.events import EventBus, default_events
from ingestor.importers.base import IMPORTER_RAN
from ingestor.sink import write_sidecar

CHECKPOINT_KEY = "drive:last_page_token"
SOURCE_NAME = "drive"


@dataclass
class DriveFile:
    id: str
    name: str
    data: bytes


class DriveClient(Protocol):
    """Talks to the actual Drive API, scoped to whichever folders it's
    configured to watch. Kept minimal and swappable so tests use a fake
    implementation instead of live Drive.

    The checkpoint is an opaque token from the client's point of view (in
    practice, a Drive Changes API pageToken), mirroring GmailClient's
    historyId-as-opaque-checkpoint shape.
    """

    def list_new_files(
        self, checkpoint: str | None
    ) -> tuple[list[DriveFile], str | None]: ...


class DriveImporter:
    """Fetches new/changed files from whichever Drive folders the DriveClient
    is configured to watch (polling) and materializes each into the Sink for
    the one FilesystemConnector to pick up; builds no Evidence tree itself
    (see ADR 0003).
    """

    def __init__(
        self,
        client: DriveClient,
        checkpoints: CheckpointStore,
        sink_root: Path,
        events: EventBus | None = None,
    ) -> None:
        self._client = client
        self._checkpoints = checkpoints
        self._sink_root = sink_root
        self._events = default_events(events)

    def pull(self) -> None:
        checkpoint = self._checkpoints.get(CHECKPOINT_KEY)
        files, next_checkpoint = self._client.list_new_files(checkpoint)
        for file in files:
            self._write(file)
        if next_checkpoint is not None and next_checkpoint != checkpoint:
            self._checkpoints.set(CHECKPOINT_KEY, next_checkpoint)
        self._events.publish(IMPORTER_RAN, importer=SOURCE_NAME, new_items=len(files))

    def _write(self, file: DriveFile) -> None:
        item_dir = self._sink_root / SOURCE_NAME / file.id
        write_sidecar(item_dir, kind="attachment", source_ref=file.id)
        (item_dir / f"00-{file.name}").write_bytes(file.data)
