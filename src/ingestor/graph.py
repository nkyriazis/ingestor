from __future__ import annotations

from typing import Any, Protocol


class GraphClient(Protocol):
    """Generic graph read/write access, backed by whatever MCP is configured.

    Deliberately minimal — mirrors the real neo4j MCP's tool surface
    (read_neo4j_cypher / write_neo4j_cypher) so the same interface works
    whether it's called directly by deterministic code (e.g. EvidenceWriter)
    or wrapped as tools for the Agent's LLM-driven tool-calling loop.
    """

    async def read_cypher(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...

    async def write_cypher(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...
