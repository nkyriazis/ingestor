from __future__ import annotations

from pathlib import Path

import pytest

from ingestor.checkpoint import InMemoryCheckpointStore
from ingestor.connectors.filesystem import FilesystemConnector
from ingestor.convert import ConvertStep
from ingestor.extract import ExtractStep
from ingestor.importers.gmail import GmailAttachment, GmailImporter, GmailMessage
from ingestor.pipeline import Pipeline, PipelineContext
from ingestor.progress import InMemoryProgressStore
from tests.fakes import FakeAgent, FakeGmailClient, FakeGraphClient

pytestmark = [pytest.mark.seam1, pytest.mark.asyncio]


async def test_a_gmail_message_flows_from_importer_through_connector_into_the_pipeline(
    tmp_path: Path,
) -> None:
    message = GmailMessage(
        id="m1",
        body_text="Nikos owns the rollout.",
        attachments=[GmailAttachment(filename="notes.txt", data=b"Ship v2 by August.")],
    )
    gmail_client = FakeGmailClient([([message], "hist-1")])
    GmailImporter(gmail_client, InMemoryCheckpointStore(), tmp_path).pull()

    [node] = FilesystemConnector(tmp_path, InMemoryCheckpointStore()).poll()

    graph = FakeGraphClient()
    agent = FakeAgent()
    ctx = PipelineContext(graph=graph, llm=None, agent=agent)  # type: ignore[arg-type]
    pipeline = Pipeline([ConvertStep(), ExtractStep()], InMemoryProgressStore())

    await pipeline.process(node, ctx)

    assert node.id == "gmail/m1"
    assert node.kind == "email"
    assert node.text is None, "the item root is just a container; the body is its own child leaf"
    body, attachment = node.children
    assert body.id == "gmail/m1/00-body.txt"
    assert body.text == "Nikos owns the rollout."
    assert attachment.id == "gmail/m1/01-notes.txt"
    assert attachment.text == "Ship v2 by August."

    written_ids = {c.params["id"] for c in graph.write_calls if "kind" in c.params}
    assert written_ids == {"gmail/m1", "gmail/m1/00-body.txt", "gmail/m1/01-notes.txt"}

    prompted_ids = {user_prompt.splitlines()[0] for _, user_prompt in agent.calls}
    assert prompted_ids == {"Evidence id: gmail/m1/00-body.txt", "Evidence id: gmail/m1/01-notes.txt"}
