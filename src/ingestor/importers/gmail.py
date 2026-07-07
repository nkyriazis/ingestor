from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ingestor.checkpoint import CheckpointStore
from ingestor.events import EventBus, default_events
from ingestor.importers.base import IMPORTER_RAN
from ingestor.sink import write_sidecar

CHECKPOINT_KEY = "gmail:last_history_id"
SOURCE_NAME = "gmail"


@dataclass
class GmailAttachment:
    filename: str
    data: bytes


@dataclass
class GmailMessage:
    id: str
    body_text: str
    attachments: list[GmailAttachment] = field(default_factory=list)


class GmailClient(Protocol):
    """Talks to the actual Gmail API. Kept minimal and swappable so tests use
    a fake implementation instead of live Gmail.

    The checkpoint is an opaque token from the client's point of view (in
    practice, a Gmail `historyId` — not orderable/comparable the way a
    message ID is), so it's returned separately from the messages rather
    than derived from them.
    """

    def list_new_messages(
        self, checkpoint: str | None
    ) -> tuple[list[GmailMessage], str | None]: ...


class GmailImporter:
    """Fetches new Gmail messages (polling — see ADR 0001's sibling trigger
    decision) and materializes each into the Sink for the one
    FilesystemConnector to pick up; builds no Evidence tree itself (see
    ADR 0003).
    """

    def __init__(
        self,
        client: GmailClient,
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
        messages, next_checkpoint = self._client.list_new_messages(checkpoint)
        for message in messages:
            self._write(message)
        if next_checkpoint is not None and next_checkpoint != checkpoint:
            self._checkpoints.set(CHECKPOINT_KEY, next_checkpoint)
        self._events.publish(IMPORTER_RAN, importer=SOURCE_NAME, new_items=len(messages))

    def _write(self, message: GmailMessage) -> None:
        item_dir = self._sink_root / SOURCE_NAME / message.id
        write_sidecar(item_dir, kind="email", source_ref=message.id)
        (item_dir / "00-body.txt").write_text(message.body_text, encoding="utf-8")
        for index, attachment in enumerate(message.attachments, start=1):
            (item_dir / f"{index:02d}-{attachment.filename}").write_bytes(attachment.data)
