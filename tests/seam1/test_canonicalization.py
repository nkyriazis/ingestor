from __future__ import annotations

import pytest

from ingestor.canonicalization import canonicalization_tool_spec, find_candidates
from tests.fakes import FakeGraphClient

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


@pytest.mark.asyncio
async def test_tool_spec_queries_the_graph_scoped_to_the_requested_type_and_reports_candidates() -> (
    None
):
    graph = FakeGraphClient(existing_by_type={"Person": [("person-nick", "Nick")]})
    tool = canonicalization_tool_spec(graph)

    result = await tool.handler({"name": "Nikos", "type": "Person"})

    assert graph.read_calls[0].params == {"type": "Person"}
    assert "person-nick" in result
    assert "Nick" in result


@pytest.mark.asyncio
async def test_tool_spec_reports_when_nothing_is_similar() -> None:
    graph = FakeGraphClient(existing_by_type={"Person": [("person-sarah", "Sarah")]})
    tool = canonicalization_tool_spec(graph)

    result = await tool.handler({"name": "Nikos", "type": "Person"})

    assert "no similar" in result.lower()
