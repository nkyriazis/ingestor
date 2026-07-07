from __future__ import annotations

import io
from pathlib import Path

from markitdown import MarkItDown

_markitdown = MarkItDown()


def convert_document_to_text(raw_bytes: bytes, filename: str) -> str:
    """Turns a document attachment's bytes into ingestable text via
    markitdown (see CONTEXT.md's Conversion entry). Structure discovery
    (splitting a file into further Evidence children) is added by later
    Steps for content types that need it, e.g. slide decks.
    """
    extension = Path(filename).suffix or None
    result = _markitdown.convert_stream(io.BytesIO(raw_bytes), file_extension=extension)
    return str(result.text_content)
