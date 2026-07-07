from __future__ import annotations

import pytest

from ingestor.checkpoint import InMemoryCheckpointStore
from ingestor.connectors.gmail import (
    CHECKPOINT_KEY,
    GmailAttachment,
    GmailConnector,
    GmailMessage,
)
from tests.fakes import FakeGmailClient

pytestmark = pytest.mark.seam1


def test_first_poll_ingests_messages_and_stores_the_returned_checkpoint() -> None:
    client = FakeGmailClient([([GmailMessage(id="m1", body_text="hello")], "hist-1")])
    checkpoints = InMemoryCheckpointStore()
    connector = GmailConnector(client, checkpoints)

    nodes = connector.poll()

    assert [node.id for node in nodes] == ["gmail:m1"]
    assert nodes[0].kind == "email"
    assert nodes[0].source_ref == "m1"
    assert nodes[0].text == "hello"
    assert checkpoints.get(CHECKPOINT_KEY) == "hist-1"


def test_first_poll_passes_no_checkpoint() -> None:
    client = FakeGmailClient([([], "hist-0")])
    connector = GmailConnector(client, InMemoryCheckpointStore())

    connector.poll()

    assert client.checkpoints_requested == [None]


def test_second_poll_reuses_the_stored_checkpoint_and_never_reingests() -> None:
    client = FakeGmailClient(
        [
            ([GmailMessage(id="m1", body_text="hello")], "hist-1"),
            ([], "hist-1"),
        ]
    )
    connector = GmailConnector(client, InMemoryCheckpointStore())

    first = connector.poll()
    second = connector.poll()

    assert [node.id for node in first] == ["gmail:m1"]
    assert second == []
    assert client.checkpoints_requested == [None, "hist-1"]


def test_attachments_become_child_evidence_nodes_contained_in_the_email() -> None:
    message = GmailMessage(
        id="m1",
        body_text="see attached",
        attachments=[
            GmailAttachment(filename="notes.docx", data=b"docx-bytes"),
            GmailAttachment(filename="budget.pdf", data=b"pdf-bytes"),
        ],
    )
    client = FakeGmailClient([([message], "hist-1")])
    connector = GmailConnector(client, InMemoryCheckpointStore())

    [email_node] = connector.poll()

    assert [child.filename for child in email_node.children] == ["notes.docx", "budget.pdf"]
    assert [child.raw_bytes for child in email_node.children] == [b"docx-bytes", b"pdf-bytes"]
    assert all(child.kind == "attachment" for child in email_node.children)
    assert all(child.text is None for child in email_node.children)


def test_an_empty_poll_does_not_move_the_checkpoint_backwards() -> None:
    checkpoints = InMemoryCheckpointStore()
    checkpoints.set(CHECKPOINT_KEY, "hist-5")
    client = FakeGmailClient([([], None)])
    connector = GmailConnector(client, checkpoints)

    connector.poll()

    assert checkpoints.get(CHECKPOINT_KEY) == "hist-5"
