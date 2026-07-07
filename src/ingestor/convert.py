from __future__ import annotations

from ingestor.evidence import EvidenceNode
from ingestor.graph import GraphClient
from ingestor.pipeline import PipelineContext

_UPSERT_NODE = """
MERGE (e:Evidence {id: $id})
SET e.kind = $kind, e.source_ref = $source_ref, e.text = $text
"""

_UPSERT_EDGE = """
MATCH (child:Evidence {id: $child_id}), (parent:Evidence {id: $parent_id})
MERGE (child)-[r:CONTAINED_IN]->(parent)
SET r.position = $position
"""


class EvidenceWriter:
    """Writes an Evidence tree into the graph: every node (container, file,
    image, text snippet) becomes its own Evidence record, linked to its
    parent via CONTAINED_IN with an ordinal position (see CONTEXT.md).
    Mechanical and deterministic — no judgment involved, so this talks to the
    GraphClient directly rather than through the Agent.
    """

    def __init__(self, graph: GraphClient) -> None:
        self._graph = graph

    async def write(self, node: EvidenceNode, parent_id: str | None = None, position: int = 0) -> None:
        await self._graph.write_cypher(
            _UPSERT_NODE,
            {"id": node.id, "kind": node.kind, "source_ref": node.source_ref, "text": node.text},
        )
        if parent_id is not None:
            await self._graph.write_cypher(
                _UPSERT_EDGE, {"child_id": node.id, "parent_id": parent_id, "position": position}
            )
        for index, child in enumerate(node.children):
            await self.write(child, parent_id=node.id, position=index)


class ConvertStep:
    """Turns a raw Evidence node's bytes into ingestable content and writes
    the resulting Evidence tree to the graph. For plain text (e.g. an email
    body), there's nothing to convert — the walking skeleton scope (issue #2)
    covers only this case; document/image conversion are added in later
    issues without changing this Step's shape.
    """

    name = "convert"

    async def run(self, node: EvidenceNode, ctx: PipelineContext) -> None:
        await EvidenceWriter(ctx.graph).write(node)
