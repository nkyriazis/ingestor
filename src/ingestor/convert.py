from __future__ import annotations

from ingestor.documents import convert_document_to_text
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
    """Turns each raw Evidence node's bytes into ingestable content and
    writes the resulting Evidence tree to the graph. Plain text (e.g. an
    email body) needs no conversion; document attachments are converted via
    markitdown. Image/slide-deck structure discovery is added by a later
    issue without changing this Step's shape.
    """

    name = "convert"

    async def run(self, node: EvidenceNode, ctx: PipelineContext) -> None:
        _convert_tree(node)
        await EvidenceWriter(ctx.graph).write(node)


def _convert_tree(node: EvidenceNode) -> None:
    if node.text is None and node.raw_bytes is not None:
        node.text = convert_document_to_text(node.raw_bytes, node.filename or "")
    for child in node.children:
        _convert_tree(child)
