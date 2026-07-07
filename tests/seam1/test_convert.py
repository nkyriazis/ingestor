from __future__ import annotations

import io
import zipfile

import pytest
from docx import Document
from pptx import Presentation
from pptx.util import Inches

from ingestor.convert import ConvertStep, EvidenceWriter
from ingestor.evidence import EvidenceNode
from ingestor.pipeline import PipelineContext
from tests.fakes import FakeGraphClient

pytestmark = [pytest.mark.seam1, pytest.mark.asyncio]


def _docx_bytes(paragraph: str) -> bytes:
    document = Document()
    document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _tiny_png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def _deck_bytes_with_one_image_slide() -> bytes:
    presentation = Presentation()
    layout = presentation.slide_layouts[5]
    slide = presentation.slides.add_slide(layout)
    slide.shapes.title.text = "Appendix"
    slide.shapes.add_picture(io.BytesIO(_tiny_png()), Inches(1), Inches(1), height=Inches(2))
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


async def _fake_caption(data: bytes, mime_type: str) -> str:
    return f"[caption of a {mime_type} image, {len(data)} bytes]"


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


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
    ctx = PipelineContext(graph=graph, llm=None, agent=None)  # type: ignore[arg-type]

    await ConvertStep().run(EvidenceNode(id="e1", kind="email", source_ref="e1", text="hi"), ctx)

    assert graph.write_calls


async def test_convert_step_converts_a_document_attachment_before_writing() -> None:
    graph = FakeGraphClient()
    ctx = PipelineContext(graph=graph, llm=None, agent=None)  # type: ignore[arg-type]
    email = EvidenceNode(
        id="gmail:e1",
        kind="email",
        source_ref="e1",
        text="see attached",
        children=[
            EvidenceNode(
                id="gmail:e1:attachment:0",
                kind="attachment",
                source_ref="notes.docx",
                filename="notes.docx",
                raw_bytes=_docx_bytes("Nikos will lead the migration."),
            )
        ],
    )

    await ConvertStep().run(email, ctx)

    assert email.children[0].text is not None
    assert "Nikos" in email.children[0].text
    node_writes = {c.params["id"]: c.params["text"] for c in graph.write_calls if "kind" in c.params}
    assert node_writes["gmail:e1:attachment:0"] and "Nikos" in node_writes["gmail:e1:attachment:0"]


async def test_a_standalone_image_attachment_is_captioned_via_the_injected_captioner() -> None:
    graph = FakeGraphClient()
    ctx = PipelineContext(graph=graph, llm=None, agent=None)  # type: ignore[arg-type]
    email = EvidenceNode(
        id="gmail:e2",
        kind="email",
        source_ref="e2",
        text="see attached",
        children=[
            EvidenceNode(
                id="gmail:e2:attachment:0",
                kind="attachment",
                source_ref="photo.png",
                filename="photo.png",
                raw_bytes=_tiny_png(),
            )
        ],
    )

    await ConvertStep(caption=_fake_caption).run(email, ctx)

    assert email.children[0].text == "[caption of a image/png image, 79 bytes]"


async def test_a_slide_deck_expands_into_slide_children_contained_in_the_deck_in_order() -> None:
    graph = FakeGraphClient()
    ctx = PipelineContext(graph=graph, llm=None, agent=None)  # type: ignore[arg-type]
    deck = EvidenceNode(
        id="gmail:e3:attachment:0",
        kind="attachment",
        source_ref="deck.pptx",
        filename="deck.pptx",
        raw_bytes=_deck_bytes_with_one_image_slide(),
    )

    await ConvertStep(caption=_fake_caption).run(deck, ctx)

    assert len(deck.children) == 1
    slide = deck.children[0]
    assert slide.kind == "slide"
    assert slide.id == "gmail:e3:attachment:0:slide:0"
    assert len(slide.children) == 1
    image = slide.children[0]
    assert image.kind == "image"
    assert image.text == "[caption of a image/png image, 79 bytes]"

    edges_by_child = {
        c.params["child_id"]: c.params
        for c in graph.write_calls
        if "CONTAINED_IN" in c.query
    }
    assert edges_by_child[slide.id] == {"child_id": slide.id, "parent_id": deck.id, "position": 0}
    assert edges_by_child[image.id] == {"child_id": image.id, "parent_id": slide.id, "position": 0}


async def test_a_zip_attachment_expands_into_one_child_per_entry() -> None:
    graph = FakeGraphClient()
    ctx = PipelineContext(graph=graph, llm=None, agent=None)  # type: ignore[arg-type]
    archive = EvidenceNode(
        id="gmail:e4:attachment:0",
        kind="attachment",
        source_ref="bundle.zip",
        filename="bundle.zip",
        raw_bytes=_zip_bytes(
            {
                "note.txt": b"Ship v2 by August.",
                "notes.docx": _docx_bytes("Nikos owns the rollout."),
            }
        ),
    )

    await ConvertStep(caption=_fake_caption).run(archive, ctx)

    assert archive.text is None, "the archive itself is a pure container"
    children_by_ref = {child.source_ref: child for child in archive.children}
    assert children_by_ref["note.txt"].text == "Ship v2 by August."
    assert "Nikos" in (children_by_ref["notes.docx"].text or "")
    assert all(child.id.startswith(archive.id) for child in archive.children)


async def test_a_pptx_inside_a_zip_is_still_expanded_into_slides() -> None:
    graph = FakeGraphClient()
    ctx = PipelineContext(graph=graph, llm=None, agent=None)  # type: ignore[arg-type]
    archive = EvidenceNode(
        id="gmail:e5:attachment:0",
        kind="attachment",
        source_ref="bundle.zip",
        filename="bundle.zip",
        raw_bytes=_zip_bytes({"deck.pptx": _deck_bytes_with_one_image_slide()}),
    )

    await ConvertStep(caption=_fake_caption).run(archive, ctx)

    [deck] = archive.children
    assert deck.filename == "deck.pptx"
    [slide] = deck.children
    assert slide.kind == "slide"
    [image] = slide.children
    assert image.text == "[caption of a image/png image, 79 bytes]"
