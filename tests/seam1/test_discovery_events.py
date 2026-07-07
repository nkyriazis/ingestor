from __future__ import annotations

from pathlib import Path

import pytest

from ingestor.checkpoint import InMemoryCheckpointStore
from ingestor.connectors.filesystem import ITEM_DISCOVERED, FilesystemConnector
from ingestor.events import EventBus
from ingestor.importers.gmail import IMPORTER_RAN, GmailImporter, GmailMessage
from ingestor.sink import write_sidecar
from tests.fakes import FakeGmailClient

pytestmark = [pytest.mark.seam1, pytest.mark.asyncio]


async def test_filesystem_connector_publishes_one_item_discovered_per_new_item(
    tmp_path: Path,
) -> None:
    bus = EventBus()
    subscription = bus.subscribe()
    write_sidecar(tmp_path / "gmail" / "m1", kind="email", source_ref="m1")
    write_sidecar(tmp_path / "gmail" / "m2", kind="email", source_ref="m2")
    connector = FilesystemConnector(tmp_path, InMemoryCheckpointStore(), events=bus)

    connector.poll()

    first = await anext(subscription)
    second = await anext(subscription)
    assert {(first.kind, first.data["item_id"]), (second.kind, second.data["item_id"])} == {
        (ITEM_DISCOVERED, "gmail/m1"),
        (ITEM_DISCOVERED, "gmail/m2"),
    }


async def test_filesystem_connector_publishes_nothing_when_no_new_items(tmp_path: Path) -> None:
    bus = EventBus()
    subscription = bus.subscribe()
    connector = FilesystemConnector(tmp_path, InMemoryCheckpointStore(), events=bus)

    connector.poll()
    bus.publish("sentinel")

    event = await anext(subscription)
    assert event.kind == "sentinel"


async def test_gmail_importer_publishes_importer_ran_with_the_new_message_count(
    tmp_path: Path,
) -> None:
    bus = EventBus()
    subscription = bus.subscribe()
    client = FakeGmailClient([([GmailMessage(id="m1", body_text="hi")], "hist-1")])

    GmailImporter(client, InMemoryCheckpointStore(), tmp_path, events=bus).pull()

    event = await anext(subscription)
    assert event.kind == IMPORTER_RAN
    assert event.data == {"importer": "gmail", "new_items": 1}


async def test_gmail_importer_reports_zero_new_items_when_nothing_new(tmp_path: Path) -> None:
    bus = EventBus()
    subscription = bus.subscribe()
    client = FakeGmailClient([([], "hist-1")])

    GmailImporter(client, InMemoryCheckpointStore(), tmp_path, events=bus).pull()

    event = await anext(subscription)
    assert event.data == {"importer": "gmail", "new_items": 0}
