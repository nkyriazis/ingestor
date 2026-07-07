from __future__ import annotations

import pytest

from ingestor.importers.drive_api import resolve_folder_id

pytestmark = pytest.mark.seam1

FOLDERS = [
    {"id": "1", "name": "Work", "parents": []},
    {"id": "2", "name": "Notes", "parents": ["1"]},  # Work/Notes
    {"id": "3", "name": "Notes", "parents": []},  # top-level Notes
    {"id": "4", "name": "Personal", "parents": []},
    {"id": "5", "name": "Notes", "parents": ["4"]},  # Personal/Notes
]


def test_resolves_an_unambiguous_bare_name() -> None:
    assert resolve_folder_id(FOLDERS, "Personal") == "4"


def test_disambiguates_same_named_folders_by_full_path() -> None:
    assert resolve_folder_id(FOLDERS, "Work/Notes") == "2"
    assert resolve_folder_id(FOLDERS, "Personal/Notes") == "5"


def test_raises_when_a_bare_name_is_ambiguous() -> None:
    with pytest.raises(ValueError, match="Ambiguous"):
        resolve_folder_id(FOLDERS, "Notes")


def test_raises_when_nothing_matches() -> None:
    with pytest.raises(ValueError, match="No Drive folder"):
        resolve_folder_id(FOLDERS, "Nonexistent")


def test_raises_when_the_path_matches_the_leaf_but_not_the_parent() -> None:
    with pytest.raises(ValueError, match="No Drive folder"):
        resolve_folder_id(FOLDERS, "Nonexistent/Notes")
