from __future__ import annotations

import pytest

from ingestor.convert import ConvertStep, EvidenceWriter
from ingestor.evidence import EvidenceNode
from ingestor.pipeline import PipelineContext
from tests.fakes import FakeGraphClient

pytestmark = [pytest.mark.seam1, pytest.mark.asyncio]


async def test_writes_a_single_node_with_no_parent_edge() -> None:
    graph = FakeGraphClient()

    await EvidenceWriter(graph).write(EvidenceNode(id="e1", kind="email", source_ref="e1", text="hi"))

    assert len(graph.write_calls) == 1
    assert graph.write_calls[0].params == {
        "id": "e1",
        "kind": "email",
        "source_ref": "e1",
        "text": "hi",
    }


async def test_writes_children_contained_in_their_parent_with_ordinal_position() -> None:
    graph = FakeGraphClient()
    tree = EvidenceNode(
        id="email-1",
        kind="email",
        source_ref="email-1",
        children=[
            EvidenceNode(id="att-0", kind="attachment", source_ref="a0"),
            EvidenceNode(id="att-1", kind="attachment", source_ref="a1"),
        ],
    )

    await EvidenceWriter(graph).write(tree)

    node_writes = [c for c in graph.write_calls if "MERGE (e:Evidence" in c.query]
    edge_writes = [c for c in graph.write_calls if "CONTAINED_IN" in c.query]
    assert {c.params["id"] for c in node_writes} == {"email-1", "att-0", "att-1"}
    assert [(c.params["child_id"], c.params["position"]) for c in edge_writes] == [
        ("att-0", 0),
        ("att-1", 1),
    ]
    assert all(c.params["parent_id"] == "email-1" for c in edge_writes)


async def test_convert_step_writes_the_evidence_tree() -> None:
    graph = FakeGraphClient()
    ctx = PipelineContext(graph=graph, agent=None)  # type: ignore[arg-type]

    await ConvertStep().run(EvidenceNode(id="e1", kind="email", source_ref="e1", text="hi"), ctx)

    assert graph.write_calls
