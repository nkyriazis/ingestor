from __future__ import annotations

from pathlib import Path

from ingestor.evidence import EvidenceKind, EvidenceNode
from ingestor.sink import SIDECAR_NAME, read_sidecar


def build_tree(directory: Path, node_id: str, default_kind: EvidenceKind = "container") -> EvidenceNode:
    """Turns a directory into an Evidence tree: nesting and sort order become
    CONTAINED_IN and position for free. A `_evidence.json` sidecar (if
    present) gives this node's `kind`/`source_ref`; otherwise `default_kind`
    and the directory's own name are used.

    Shared by FilesystemConnector (reading the Sink, where the top-level
    item directory always has a sidecar from its Importer) and archive
    expansion in Convert (reading a temp-extracted archive, which has no
    sidecars at all) — see ADR 0004. One tree-building implementation,
    two sources of directories to point it at.
    """
    sidecar_path = directory / SIDECAR_NAME
    if sidecar_path.exists():
        sidecar = read_sidecar(directory)
        kind, source_ref = sidecar.kind, sidecar.source_ref
    else:
        kind, source_ref = default_kind, directory.name

    node = EvidenceNode(id=node_id, kind=kind, source_ref=source_ref)
    children = sorted(p for p in directory.iterdir() if p.name != SIDECAR_NAME)
    node.children = [_build_child(path, f"{node_id}/{path.name}") for path in children]
    return node


def _build_child(path: Path, node_id: str) -> EvidenceNode:
    if path.is_dir():
        return build_tree(path, node_id)
    if path.suffix == ".txt":
        return EvidenceNode(
            id=node_id, kind="attachment", source_ref=path.name, text=path.read_text(encoding="utf-8")
        )
    return EvidenceNode(
        id=node_id,
        kind="attachment",
        source_ref=path.name,
        filename=path.name,
        raw_bytes=path.read_bytes(),
    )
