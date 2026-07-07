from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from ingestor.captioning import caption_image
from ingestor.documents import convert_document_to_text
from ingestor.evidence import EvidenceNode
from ingestor.graph import GraphClient
from ingestor.pipeline import PipelineContext
from ingestor.slides import extract_slides

CaptionFn = Callable[[bytes, str], Awaitable[str]]

_IMAGE_MIME_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}

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
    email body) needs no conversion. Document attachments are converted via
    markitdown; slide decks (.pptx) are split into one Evidence child per
    slide (CONTAINED_IN the deck, in order), with embedded pictures becoming
    further children of their slide; standalone images and embedded slide
    pictures alike get a text description via the vision-capable Agent
    model, so later Steps only ever reason over text (see CONTEXT.md's
    Conversion entry).
    """

    name = "convert"

    def __init__(self, caption: CaptionFn | None = None) -> None:
        # Overridable so Seam 1 tests can verify structure discovery/dispatch
        # deterministically without a real vision model call; production
        # leaves this unset and captions via ctx.llm for real.
        self._caption_override = caption

    async def run(self, node: EvidenceNode, ctx: PipelineContext) -> None:
        caption = self._caption_override or (
            lambda data, mime: caption_image(ctx.llm, data, mime)
        )
        await _convert_tree(node, caption)
        await EvidenceWriter(ctx.graph).write(node)


async def _convert_tree(node: EvidenceNode, caption: CaptionFn) -> None:
    if node.text is None and node.raw_bytes is not None:
        extension = Path(node.filename or "").suffix.lower().lstrip(".")
        if extension == "pptx":
            _expand_slide_deck(node)
        elif extension in _IMAGE_MIME_TYPES:
            node.text = await caption(node.raw_bytes, _IMAGE_MIME_TYPES[extension])
        else:
            node.text = convert_document_to_text(node.raw_bytes, node.filename or "")

    for child in node.children:
        await _convert_tree(child, caption)


def _expand_slide_deck(node: EvidenceNode) -> None:
    assert node.raw_bytes is not None
    for slide_index, slide in enumerate(extract_slides(node.raw_bytes)):
        slide_id = f"{node.id}:slide:{slide_index}"
        slide_node = EvidenceNode(id=slide_id, kind="slide", source_ref=f"slide-{slide_index}")
        if slide.text:
            slide_node.text = slide.text
        slide_node.children = [
            EvidenceNode(
                id=f"{slide_id}:image:{image_index}",
                kind="image",
                source_ref=f"image-{image_index}",
                raw_bytes=image.data,
                filename=f"slide-{slide_index}-image-{image_index}.{image.extension}",
            )
            for image_index, image in enumerate(slide.images)
        ]
        node.children.append(slide_node)
