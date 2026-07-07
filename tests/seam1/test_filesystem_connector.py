from __future__ import annotations

from pathlib import Path

import pytest

from ingestor.checkpoint import InMemoryCheckpointStore
from ingestor.connectors.filesystem import FilesystemConnector
from ingestor.sink import write_sidecar

pytestmark = pytest.mark.seam1


def test_an_empty_or_missing_sink_yields_nothing(tmp_path: Path) -> None:
    connector = FilesystemConnector(tmp_path / "does-not-exist", InMemoryCheckpointStore())

    assert connector.poll() == []


def test_builds_an_item_from_its_sidecar_and_flat_children(tmp_path: Path) -> None:
    item_dir = tmp_path / "gmail" / "msg-1"
    write_sidecar(item_dir, kind="email", source_ref="msg-1")
    (item_dir / "00-body.txt").write_text("hello there", encoding="utf-8")
    (item_dir / "01-notes.docx").write_bytes(b"docx-bytes")

    [node] = FilesystemConnector(tmp_path, InMemoryCheckpointStore()).poll()

    assert node.id == "gmail/msg-1"
    assert node.kind == "email"
    assert node.source_ref == "msg-1"
    assert [child.id for child in node.children] == [
        "gmail/msg-1/00-body.txt",
        "gmail/msg-1/01-notes.docx",
    ]
    body, attachment = node.children
    assert body.text == "hello there"
    assert body.raw_bytes is None
    assert attachment.text is None
    assert attachment.raw_bytes == b"docx-bytes"
    assert attachment.filename == "01-notes.docx"
    assert all(child.kind == "attachment" for child in node.children)


def test_never_re_ingests_an_item_it_has_already_handed_off(tmp_path: Path) -> None:
    item_dir = tmp_path / "gmail" / "msg-1"
    write_sidecar(item_dir, kind="email", source_ref="msg-1")
    (item_dir / "00-body.txt").write_text("hello", encoding="utf-8")
    checkpoints = InMemoryCheckpointStore()
    connector = FilesystemConnector(tmp_path, checkpoints)

    first = connector.poll()
    second = connector.poll()

    assert len(first) == 1
    assert second == []


def test_a_second_new_item_is_picked_up_on_a_later_poll(tmp_path: Path) -> None:
    checkpoints = InMemoryCheckpointStore()
    connector = FilesystemConnector(tmp_path, checkpoints)
    write_sidecar(tmp_path / "gmail" / "msg-1", kind="email", source_ref="msg-1")
    connector.poll()

    write_sidecar(tmp_path / "gmail" / "msg-2", kind="email", source_ref="msg-2")
    second = connector.poll()

    assert [node.id for node in second] == ["gmail/msg-2"]


def test_items_from_different_sources_are_both_picked_up(tmp_path: Path) -> None:
    write_sidecar(tmp_path / "gmail" / "msg-1", kind="email", source_ref="msg-1")
    write_sidecar(tmp_path / "keep" / "note-1", kind="email", source_ref="note-1")

    nodes = FilesystemConnector(tmp_path, InMemoryCheckpointStore()).poll()

    assert {node.id for node in nodes} == {"gmail/msg-1", "keep/note-1"}
