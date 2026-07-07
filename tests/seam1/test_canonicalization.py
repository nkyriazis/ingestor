from __future__ import annotations

import pytest

from ingestor.canonicalization import find_candidates

pytestmark = pytest.mark.seam1


def test_finds_a_near_miss_alias() -> None:
    existing = [("k1", "Nick"), ("k2", "Sarah")]

    candidates = find_candidates("Nikos", existing)

    assert [c.id for c in candidates] == ["k1"]


def test_no_candidates_below_the_threshold() -> None:
    existing = [("k1", "Zzz Totally Different")]

    assert find_candidates("Nikos", existing) == []


def test_ranks_the_closest_match_first() -> None:
    existing = [("k1", "Nikolas"), ("k2", "Nikos")]

    candidates = find_candidates("Nikos", existing)

    assert candidates[0].id == "k2"
    assert candidates[0].similarity >= candidates[1].similarity


def test_same_input_always_surfaces_the_same_candidates() -> None:
    existing = [("k1", "Nick"), ("k2", "Nikos")]

    first = find_candidates("Nikolaos", existing)
    second = find_candidates("Nikolaos", existing)

    assert first == second
