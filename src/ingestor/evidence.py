from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvidenceNode:
    """A raw source artifact: an email, an attachment, an image, a text snippet.

    Captures provenance, not meaning (see CONTEXT.md). Every node in a source's
    content tree is its own EvidenceNode, including containers; children are
    linked to their parent via CONTAINED_IN with an ordinal position when
    written to the graph (see ingestor.convert.EvidenceWriter).
    """

    id: str
    kind: str
    source_ref: str
    text: str | None = None
    children: list[EvidenceNode] = field(default_factory=list)
    raw_bytes: bytes | None = None
    filename: str | None = None
