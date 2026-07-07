from __future__ import annotations

from pathlib import Path

import pytest

from ingestor.directory_tree import build_tree
from ingestor.sink import write_sidecar

pytestmark = pytest.mark.seam1


def test_uses_the_sidecar_when_present(tmp_path: Path) -> None:
    write_sidecar(tmp_path, kind="email", source_ref="msg-1")
    (tmp_path / "00-body.txt").write_text("hi", encoding="utf-8")

    node = build_tree(tmp_path, "root")

    assert node.kind == "email"
    assert node.source_ref == "msg-1"


def test_falls_back_to_a_default_kind_and_directory_name_without_a_sidecar(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("hi", encoding="utf-8")

    node = build_tree(tmp_path, "root", default_kind="container")

    assert node.kind == "container"
    assert node.source_ref == tmp_path.name


def test_children_are_ordered_and_ids_are_nested_under_the_parent(tmp_path: Path) -> None:
    (tmp_path / "00-a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "01-b.txt").write_text("b", encoding="utf-8")

    node = build_tree(tmp_path, "root")

    assert [child.id for child in node.children] == ["root/00-a.txt", "root/01-b.txt"]
    assert [child.text for child in node.children] == ["a", "b"]


def test_nested_subdirectories_become_nested_container_nodes(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "file.txt").write_text("nested", encoding="utf-8")

    node = build_tree(tmp_path, "root")

    [sub_node] = node.children
    assert sub_node.kind == "container"
    assert sub_node.id == "root/sub"
    assert [c.id for c in sub_node.children] == ["root/sub/file.txt"]
    assert sub_node.children[0].text == "nested"


def test_non_text_files_are_read_as_raw_bytes_with_their_filename(tmp_path: Path) -> None:
    (tmp_path / "notes.docx").write_bytes(b"docx-bytes")

    node = build_tree(tmp_path, "root")

    [child] = node.children
    assert child.filename == "notes.docx"
    assert child.raw_bytes == b"docx-bytes"
    assert child.text is None
