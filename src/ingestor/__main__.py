from __future__ import annotations

import asyncio
import os
from pathlib import Path

from ingestor.agent import Agent
from ingestor.canonicalization import canonicalization_tool_spec
from ingestor.checkpoint import JsonFileCheckpointStore
from ingestor.connectors.gmail import GmailConnector
from ingestor.connectors.gmail_api import RealGmailClient
from ingestor.convert import ConvertStep
from ingestor.extract import ExtractStep
from ingestor.llm import LlamaCppClient
from ingestor.mcp_tools import McpGraphClient, connect_mcp, mcp_agent_tools
from ingestor.pipeline import Pipeline, PipelineContext
from ingestor.progress import JsonFileProgressStore

POLL_INTERVAL_SECONDS = 60
STATE_DIR = Path(os.environ.get("INGESTOR_STATE_DIR", "/var/lib/ingestor"))


async def run() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    llm = LlamaCppClient(
        base_url=os.environ["LLAMACPP_BASE_URL"],
        model=os.environ.get("LLAMACPP_MODEL", "default"),
    )
    connector = GmailConnector(
        client=RealGmailClient(Path(os.environ["GMAIL_TOKEN_PATH"])),
        checkpoints=JsonFileCheckpointStore(STATE_DIR / "gmail-checkpoint.json"),
    )
    progress = JsonFileProgressStore(STATE_DIR / "pipeline-progress.json")

    async with connect_mcp(os.environ["GRAPH_MCP_URL"]) as session:
        graph = McpGraphClient(session)
        agent = Agent(llm, tools=[canonicalization_tool_spec(graph), *await mcp_agent_tools(session)])
        pipeline = Pipeline(steps=[ConvertStep(), ExtractStep()], progress=progress)
        ctx = PipelineContext(graph=graph, llm=llm, agent=agent)

        while True:
            for node in connector.poll():
                await pipeline.process(node, ctx)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run())
