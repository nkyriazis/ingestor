from __future__ import annotations

from pathlib import Path

import pytest

from ingestor.checkpoint import InMemoryCheckpointStore
from ingestor.importers.drive import CHECKPOINT_KEY, DriveFile, DriveImporter
from ingestor.sink import SIDECAR_NAME, read_sidecar
from tests.fakes import FakeDriveClient

pytestmark = pytest.mark.seam1


def test_writes_a_new_file_into_the_sink_with_a_sidecar(tmp_path: Path) -> None:
    client = FakeDriveClient([([DriveFile(id="f1", name="notes.docx", data=b"docx-bytes")], "tok-1")])
    DriveImporter(client, InMemoryCheckpointStore(), tmp_path).pull()

    item_dir = tmp_path / "drive" / "f1"
    sidecar = read_sidecar(item_dir)
    assert sidecar.kind == "attachment"
    assert sidecar.source_ref == "f1"
    assert (item_dir / "00-notes.docx").read_bytes() == b"docx-bytes"
    names = sorted(p.name for p in item_dir.iterdir())
    assert names == ["00-notes.docx", SIDECAR_NAME]


def test_reuses_the_stored_drive_checkpoint_and_never_re_pulls(tmp_path: Path) -> None:
    client = FakeDriveClient(
        [
            ([DriveFile(id="f1", name="a.pdf", data=b"a")], "tok-1"),
            ([], "tok-1"),
        ]
    )
    checkpoints = InMemoryCheckpointStore()
    importer = DriveImporter(client, checkpoints, tmp_path)

    importer.pull()
    importer.pull()

    assert client.checkpoints_requested == [None, "tok-1"]
    assert checkpoints.get(CHECKPOINT_KEY) == "tok-1"


def test_an_empty_pull_does_not_move_the_checkpoint_backwards(tmp_path: Path) -> None:
    checkpoints = InMemoryCheckpointStore()
    checkpoints.set(CHECKPOINT_KEY, "tok-5")
    client = FakeDriveClient([([], None)])

    DriveImporter(client, checkpoints, tmp_path).pull()

    assert checkpoints.get(CHECKPOINT_KEY) == "tok-5"
