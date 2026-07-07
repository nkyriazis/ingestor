from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolSpec:
    """A single tool the Agent may call. `handler` is invoked locally with the
    LLM's parsed arguments; production wiring backs some ToolSpecs with a
    real MCP session (see ingestor.mcp_tools) and others (e.g. canonicalization
    search) with plain local functions — the Agent doesn't distinguish.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[str]]

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }
