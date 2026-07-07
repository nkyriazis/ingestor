from __future__ import annotations

from typing import Protocol

from ingestor.evidence import EvidenceNode


class Connector(Protocol):
    """A pluggable adapter for one external source (Gmail, Keep, a folder,
    etc). Detects new/changed content via whichever trigger mechanism fits
    that source and yields it as a normalized content tree. Owns its own
    checkpoint state internally — see ingestor.checkpoint.CheckpointStore.
    """

    def poll(self) -> list[EvidenceNode]: ...
