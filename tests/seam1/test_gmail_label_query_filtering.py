from __future__ import annotations

import pytest

from ingestor.importers.gmail_api import filter_by_query, resolve_label_id, resolve_label_scope

pytestmark = pytest.mark.seam1


def test_resolve_label_id_finds_a_matching_label_by_name() -> None:
    labels = [{"id": "Label_1", "name": "Work"}, {"id": "INBOX", "name": "INBOX"}]

    assert resolve_label_id(labels, "Work") == "Label_1"


def test_resolve_label_id_raises_when_no_label_matches() -> None:
    with pytest.raises(ValueError, match="Nonexistent"):
        resolve_label_id([{"id": "INBOX", "name": "INBOX"}], "Nonexistent")


def test_filter_by_query_keeps_only_ids_gmail_reports_as_matching() -> None:
    assert filter_by_query(["a", "b", "c"], {"a", "c"}) == ["a", "c"]


def test_filter_by_query_preserves_discovery_order() -> None:
    assert filter_by_query(["c", "a"], {"a", "c"}) == ["c", "a"]


def test_filter_by_query_drops_everything_when_nothing_matches() -> None:
    assert filter_by_query(["a", "b"], set()) == []


def test_resolve_label_scope_defaults_to_inbox_when_nothing_configured() -> None:
    assert resolve_label_scope(None, None) == "INBOX"


def test_resolve_label_scope_uses_the_resolved_label_regardless_of_query() -> None:
    assert resolve_label_scope("Label_123", None) == "Label_123"
    assert resolve_label_scope("Label_123", "from:someone@example.com") == "Label_123"


def test_resolve_label_scope_has_no_label_restriction_for_query_only() -> None:
    assert resolve_label_scope(None, "from:someone@example.com") is None
