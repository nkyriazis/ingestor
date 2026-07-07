from __future__ import annotations

import json
from typing import Any

from ingestor.events import EventBus
from ingestor.llm import LlamaCppClient
from ingestor.tools import ToolSpec

TOOL_CALLED = "tool_called"
AGENT_FINISHED = "agent_finished"


class AgentTurnLimitExceeded(RuntimeError):
    pass


class Agent:
    """The LLM-driven reasoning component behind judgment-requiring work
    (captioning, Canonicalization's decision, Knowledge extraction). Where a
    task needs to write to the graph, the Agent performs that write itself by
    calling tools directly — see CONTEXT.md's Agent entry. The Pipeline
    doesn't know this loop exists.
    """

    def __init__(
        self,
        llm: LlamaCppClient,
        tools: list[ToolSpec],
        max_turns: int = 8,
        events: EventBus | None = None,
    ) -> None:
        self._llm = llm
        self._tools_by_name = {tool.name: tool for tool in tools}
        self._tool_defs = [tool.to_openai_schema() for tool in tools]
        self._max_turns = max_turns
        self._events = events or EventBus()

    async def run(self, system_prompt: str, user_prompt: str) -> str:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        for _ in range(self._max_turns):
            result = await self._llm.chat(messages, tools=self._tool_defs or None)
            if not result.tool_calls:
                self._events.publish(AGENT_FINISHED, summary=result.content)
                return result.content

            messages.append(
                {
                    "role": "assistant",
                    "content": result.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in result.tool_calls
                    ],
                }
            )
            for call in result.tool_calls:
                self._events.publish(TOOL_CALLED, name=call.name, arguments=call.arguments)
                tool = self._tools_by_name.get(call.name)
                output = (
                    await tool.handler(call.arguments)
                    if tool is not None
                    else f"Unknown tool: {call.name}"
                )
                messages.append({"role": "tool", "tool_call_id": call.id, "content": output})

        raise AgentTurnLimitExceeded(f"Exceeded {self._max_turns} turns without a final answer")
