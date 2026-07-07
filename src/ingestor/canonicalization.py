from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any

from ingestor.graph import GraphClient
from ingestor.tools import ToolSpec

DEFAULT_THRESHOLD = 0.6


@dataclass
class Candidate:
    id: str
    name: str
    similarity: float


def find_candidates(
    name: str,
    existing: list[tuple[str, str]],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[Candidate]:
    """Deterministic name/alias similarity search (see CONTEXT.md's
    Canonicalization entry) — no LLM call, same input always surfaces the
    same candidates. `existing` is a list of (id, name) pairs to compare
    against; the reuse-vs-create judgment call itself belongs to the Agent.
    """
    candidates = [
        Candidate(id=existing_id, name=existing_name, similarity=ratio)
        for existing_id, existing_name in existing
        if (ratio := _similarity(name, existing_name)) >= threshold
    ]
    return sorted(candidates, key=lambda c: -c.similarity)


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


_EXISTING_NAMES_QUERY = "MATCH (n:Knowledge {type: $type}) RETURN n.id AS id, n.name AS name"


def canonicalization_tool_spec(graph: GraphClient) -> ToolSpec:
    """Builds the Agent tool that runs the deterministic candidate search
    against the live graph, so the reuse-vs-create decision is informed
    rather than blind (see CONTEXT.md's Canonicalization entry).
    """

    async def handler(arguments: dict[str, Any]) -> str:
        rows = await graph.read_cypher(_EXISTING_NAMES_QUERY, {"type": arguments["type"]})
        existing = [(row["id"], row["name"]) for row in rows]
        candidates = find_candidates(arguments["name"], existing)
        if not candidates:
            return "No similar existing nodes found."
        return "\n".join(
            f"- id={c.id} name={c.name!r} similarity={c.similarity:.2f}" for c in candidates
        )

    return ToolSpec(
        name="find_canonicalization_candidates",
        description=(
            "Deterministic name/alias similarity search over existing Knowledge "
            "nodes of a given type. Call this before minting any new Knowledge "
            "node, to check whether it already exists under a different name."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The candidate entity name."},
                "type": {
                    "type": "string",
                    "description": "The Knowledge node type, e.g. Person, Project.",
                },
            },
            "required": ["name", "type"],
        },
        handler=handler,
    )
