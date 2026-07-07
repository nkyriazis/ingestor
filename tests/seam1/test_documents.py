from __future__ import annotations

import io

import pytest
from docx import Document

from ingestor.documents import convert_document_to_text

pytestmark = pytest.mark.seam1


def _docx_bytes(paragraph: str) -> bytes:
    document = Document()
    document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_converts_a_docx_attachment_to_text() -> None:
    text = convert_document_to_text(
        _docx_bytes("Nikos will lead the Q3 migration project."), "notes.docx"
    )

    assert "Nikos" in text
    assert "migration project" in text


def test_same_input_produces_the_same_text() -> None:
    raw = _docx_bytes("Deterministic content.")

    first = convert_document_to_text(raw, "notes.docx")
    second = convert_document_to_text(raw, "notes.docx")

    assert first == second
