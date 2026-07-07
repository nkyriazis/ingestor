from __future__ import annotations

import asyncio
import os
from pathlib import Path

import uvicorn

from ingestor.agent import Agent
from ingestor.canonicalization import canonicalization_tool_spec
from ingestor.checkpoint import JsonFileCheckpointStore
from ingestor.connectors.filesystem import FilesystemConnector
from ingestor.convert import ConvertStep
from ingestor.events import EventBus
from ingestor.extract import ExtractStep
from ingestor.importers.base import Importer
from ingestor.importers.drive import DriveImporter
from ingestor.importers.drive_api import RealDriveClient
from ingestor.importers.gmail import GmailImporter
from ingestor.importers.gmail_api import RealGmailClient
from ingestor.llm import LlamaCppClient
from ingestor.mcp_tools import McpGraphClient, connect_mcp, mcp_agent_tools
from ingestor.observability import create_app
from ingestor.pipeline import Pipeline, PipelineContext
from ingestor.progress import JsonFileProgressStore

POLL_INTERVAL_SECONDS = 60
STATE_DIR = Path(os.environ.get("INGESTOR_STATE_DIR", "/var/lib/ingestor"))
SINK_ROOT = Path(os.environ.get("INGESTOR_SINK_DIR", "/var/lib/ingestor/sink"))
# 0.0.0.0 so docker-compose's port publishing can reach this at all (Docker
# forwards to a container's real interface, never its loopback) — the
# "loopback-only, no auth" guarantee (see ingestor/observability.py) is
# enforced by docker-compose's "127.0.0.1:8090:8090" host-side binding, not
# by this bind address. Running this module outside Docker would need its
# own care around that.
EVENTS_HOST = os.environ.get("INGESTOR_EVENTS_HOST", "0.0.0.0")
EVENTS_PORT = int(os.environ.get("INGESTOR_EVENTS_PORT", "8090"))


async def run() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SINK_ROOT.mkdir(parents=True, exist_ok=True)
    llm = LlamaCppClient(
        base_url=os.environ["LLAMACPP_BASE_URL"],
        model=os.environ.get("LLAMACPP_MODEL", "default"),
    )
    events = EventBus()
    importers: list[Importer] = [
        GmailImporter(
            client=RealGmailClient(
                Path(os.environ["GOOGLE_TOKEN_PATH"]),
                # `or None`: docker-compose substitutes an empty string, not
                # an absent key, for an unset optional env var.
                label=os.environ.get("GMAIL_LABEL") or None,
                query=os.environ.get("GMAIL_QUERY") or None,
            ),
            checkpoints=JsonFileCheckpointStore(STATE_DIR / "gmail-checkpoint.json"),
            sink_root=SINK_ROOT,
            events=events,
        ),
    ]
    # Drive has no sane "watch everything" default the way Gmail's inbox is
    # — it only joins the run once the user has told it which folder(s).
    drive_folders = [f.strip() for f in os.environ.get("DRIVE_FOLDERS", "").split(",") if f.strip()]
    if drive_folders:
        importers.append(
            DriveImporter(
                client=RealDriveClient(Path(os.environ["GOOGLE_TOKEN_PATH"]), drive_folders),
                checkpoints=JsonFileCheckpointStore(STATE_DIR / "drive-checkpoint.json"),
                sink_root=SINK_ROOT,
                events=events,
            )
        )
    connector = FilesystemConnector(
        sink_root=SINK_ROOT,
        checkpoints=JsonFileCheckpointStore(STATE_DIR / "filesystem-checkpoint.json"),
        events=events,
    )
    progress = JsonFileProgressStore(STATE_DIR / "pipeline-progress.json")

    events_server = uvicorn.Server(
        uvicorn.Config(create_app(events), host=EVENTS_HOST, port=EVENTS_PORT, log_level="info")
    )
    # asyncio only holds a weak reference to tasks created this way — keep
    # events_task alive for the life of the process or it can be GC'd mid-run.
    events_task = asyncio.create_task(events_server.serve())

    async with connect_mcp(os.environ["GRAPH_MCP_URL"]) as session:
        graph = McpGraphClient(session)
        agent = Agent(
            llm,
            tools=[canonicalization_tool_spec(graph), *await mcp_agent_tools(session)],
            events=events,
        )
        pipeline = Pipeline(steps=[ConvertStep(), ExtractStep()], progress=progress, events=events)
        ctx = PipelineContext(graph=graph, llm=llm, agent=agent)

        while True:
            for importer in importers:
                importer.pull()
            # No concurrency cap: independent items are fully independent,
            # and congestion is expected to occur naturally at the LLM
            # server rather than something our code should guard against.
            # return_exceptions=True so one item's failure (already visible
            # via its own step_failed event) can't crash the whole loop or
            # stop other concurrently-running items from completing.
            await asyncio.gather(
                *(pipeline.process(node, ctx) for node in connector.poll()),
                return_exceptions=True,
            )
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run())
