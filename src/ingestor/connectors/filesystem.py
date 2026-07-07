from __future__ import annotations

import json
from pathlib import Path

from ingestor.checkpoint import CheckpointStore
from ingestor.evidence import EvidenceNode
from ingestor.sink import SIDECAR_NAME, read_sidecar

CHECKPOINT_KEY = "filesystem:seen_items"


class FilesystemConnector:
    """The one Connector implementation (see ADR 0003 / CONTEXT.md): turns
    the Sink's directory structure into a normalized Evidence tree, shared
    by every Importer. Its checkpoint (which sink item directories it's
    already handed off) is independent of any Importer's own checkpoint.
    """

    def __init__(self, sink_root: Path, checkpoints: CheckpointStore) -> None:
        self._sink_root = sink_root
        self._checkpoints = checkpoints

    def poll(self) -> list[EvidenceNode]:
        if not self._sink_root.is_dir():
            return []

        seen = set(json.loads(self._checkpoints.get(CHECKPOINT_KEY) or "[]"))
        new_item_dirs = [
            item_dir
            for source_dir in sorted(p for p in self._sink_root.iterdir() if p.is_dir())
            for item_dir in sorted(p for p in source_dir.iterdir() if p.is_dir())
            if str(item_dir.relative_to(self._sink_root)) not in seen
        ]
        if not new_item_dirs:
            return []

        seen.update(str(item_dir.relative_to(self._sink_root)) for item_dir in new_item_dirs)
        self._checkpoints.set(CHECKPOINT_KEY, json.dumps(sorted(seen)))
        return [self._build_item(item_dir) for item_dir in new_item_dirs]

    def _build_item(self, item_dir: Path) -> EvidenceNode:
        sidecar = read_sidecar(item_dir)
        item_id = str(item_dir.relative_to(self._sink_root))
        node = EvidenceNode(id=item_id, kind=sidecar.kind, source_ref=sidecar.source_ref)
        children = sorted(p for p in item_dir.iterdir() if p.name != SIDECAR_NAME)
        node.children = [self._build_leaf(path, f"{item_id}/{path.name}") for path in children]
        return node

    def _build_leaf(self, path: Path, leaf_id: str) -> EvidenceNode:
        if path.suffix == ".txt":
            return EvidenceNode(
                id=leaf_id,
                kind="attachment",
                source_ref=path.name,
                text=path.read_text(encoding="utf-8"),
            )
        return EvidenceNode(
            id=leaf_id,
            kind="attachment",
            source_ref=path.name,
            filename=path.name,
            raw_bytes=path.read_bytes(),
        )
