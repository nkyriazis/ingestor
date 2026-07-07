from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

from ingestor.evidence import EvidenceKind

SIDECAR_NAME = "_evidence.json"


@dataclass
class SidecarData:
    kind: EvidenceKind
    source_ref: str


def write_sidecar(item_dir: Path, kind: EvidenceKind, source_ref: str) -> None:
    """The single source of truth for the Importer/Connector sidecar format
    (see ADR 0003) — every Importer writes it, the one FilesystemConnector
    reads it, so the format only needs to be right in one place.
    """
    item_dir.mkdir(parents=True, exist_ok=True)
    (item_dir / SIDECAR_NAME).write_text(json.dumps({"kind": kind, "source_ref": source_ref}))


def read_sidecar(item_dir: Path) -> SidecarData:
    raw = dict(json.loads((item_dir / SIDECAR_NAME).read_text()))
    kind = raw["kind"]
    if kind not in get_args(EvidenceKind):
        raise ValueError(f"{item_dir / SIDECAR_NAME}: unknown kind {kind!r}")
    return SidecarData(kind=kind, source_ref=raw["source_ref"])
