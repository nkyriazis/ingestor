from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCall]


class LlamaCppClient:
    """Thin client for a local llama.cpp server's OpenAI-compatible
    /v1/chat/completions endpoint (tool-calling, vision-capable model —
    see ADR 0002). Not a hosted API client on purpose.
    """

    def __init__(
        self, base_url: str, model: str, http_client: httpx.AsyncClient | None = None
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._http = http_client or httpx.AsyncClient(timeout=120.0)

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": 1024,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = await self._http.post(f"{self._base_url}/chat/completions", json=payload)
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]

        raw_calls = message.get("tool_calls") or []
        tool_calls = [
            ToolCall(
                id=call["id"],
                name=call["function"]["name"],
                arguments=json.loads(call["function"]["arguments"] or "{}"),
            )
            for call in raw_calls
        ]
        return ChatResult(content=message.get("content") or "", tool_calls=tool_calls)
