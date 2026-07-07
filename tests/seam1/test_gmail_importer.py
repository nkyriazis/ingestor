from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestor.checkpoint import InMemoryCheckpointStore
from ingestor.importers.gmail import (
    CHECKPOINT_KEY,
    GmailAttachment,
    GmailImporter,
    GmailMessage,
)
from ingestor.sink import SIDECAR_NAME, read_sidecar
from tests.fakes import FakeGmailClient

pytestmark = pytest.mark.seam1


def test_writes_a_new_message_into_the_sink_with_a_sidecar_and_body(tmp_path: Path) -> None:
    client = FakeGmailClient([([GmailMessage(id="m1", body_text="hello")], "hist-1")])
    GmailImporter(client, InMemoryCheckpointStore(), tmp_path).pull()

    item_dir = tmp_path / "gmail" / "m1"
    sidecar = json.loads((item_dir / SIDECAR_NAME).read_text())
    assert sidecar == {"kind": "email", "source_ref": "m1"}
    assert read_sidecar(item_dir).kind == "email"
    assert (item_dir / "00-body.txt").read_text(encoding="utf-8") == "hello"


def test_writes_attachments_as_numbered_files_after_the_body(tmp_path: Path) -> None:
    message = GmailMessage(
        id="m2",
        body_text="see attached",
        attachments=[
            GmailAttachment(filename="notes.docx", data=b"docx-bytes"),
            GmailAttachment(filename="budget.pdf", data=b"pdf-bytes"),
        ],
    )
    client = FakeGmailClient([([message], "hist-1")])
    GmailImporter(client, InMemoryCheckpointStore(), tmp_path).pull()

    item_dir = tmp_path / "gmail" / "m2"
    assert (item_dir / "01-notes.docx").read_bytes() == b"docx-bytes"
    assert (item_dir / "02-budget.pdf").read_bytes() == b"pdf-bytes"
    names = sorted(p.name for p in item_dir.iterdir())
    assert names == ["00-body.txt", "01-notes.docx", "02-budget.pdf", SIDECAR_NAME]


def test_reuses_the_stored_gmail_checkpoint_and_never_re_pulls(tmp_path: Path) -> None:
    client = FakeGmailClient(
        [
            ([GmailMessage(id="m1", body_text="hello")], "hist-1"),
            ([], "hist-1"),
        ]
    )
    checkpoints = InMemoryCheckpointStore()
    importer = GmailImporter(client, checkpoints, tmp_path)

    importer.pull()
    importer.pull()

    assert client.checkpoints_requested == [None, "hist-1"]
    assert checkpoints.get(CHECKPOINT_KEY) == "hist-1"


def test_an_empty_pull_does_not_move_the_checkpoint_backwards(tmp_path: Path) -> None:
    checkpoints = InMemoryCheckpointStore()
    checkpoints.set(CHECKPOINT_KEY, "hist-5")
    client = FakeGmailClient([([], None)])

    GmailImporter(client, checkpoints, tmp_path).pull()

    assert checkpoints.get(CHECKPOINT_KEY) == "hist-5"
