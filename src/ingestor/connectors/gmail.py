from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ingestor.checkpoint import CheckpointStore
from ingestor.evidence import EvidenceNode

CHECKPOINT_KEY = "gmail:last_message_id"


@dataclass
class GmailMessage:
    id: str
    body_text: str


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


class GmailConnector:
    """Polling Connector for Gmail (see ADR 0001's sibling design decision:
    polling over push, since personal-scale latency doesn't matter).
    """

    def __init__(self, client: GmailClient, checkpoints: CheckpointStore) -> None:
        self._client = client
        self._checkpoints = checkpoints

    def poll(self) -> list[EvidenceNode]:
        checkpoint = self._checkpoints.get(CHECKPOINT_KEY)
        messages, next_checkpoint = self._client.list_new_messages(checkpoint)
        if next_checkpoint is not None and next_checkpoint != checkpoint:
            self._checkpoints.set(CHECKPOINT_KEY, next_checkpoint)
        return [
            EvidenceNode(
                id=f"gmail:{message.id}",
                kind="email",
                source_ref=message.id,
                text=message.body_text,
            )
            for message in messages
        ]
