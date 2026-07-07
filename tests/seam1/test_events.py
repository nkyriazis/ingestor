from __future__ import annotations

import asyncio

import pytest

from ingestor.events import EventBus

pytestmark = [pytest.mark.seam1, pytest.mark.asyncio]


async def test_a_subscriber_receives_a_published_event() -> None:
    bus = EventBus()
    subscription = bus.subscribe()

    bus.publish("thing_happened", foo="bar")

    event = await anext(subscription)
    assert event.kind == "thing_happened"
    assert event.data == {"foo": "bar"}


async def test_a_subscriber_never_sees_events_published_before_it_subscribed() -> None:
    bus = EventBus()
    bus.publish("before", n=1)
    subscription = bus.subscribe()
    bus.publish("after", n=2)

    event = await anext(subscription)
    assert event.data == {"n": 2}


async def test_publishing_with_no_subscribers_is_a_no_op() -> None:
    bus = EventBus()

    bus.publish("nobody_is_listening")  # must not raise


async def test_every_event_is_fanned_out_to_every_subscriber() -> None:
    bus = EventBus()
    sub_a = bus.subscribe()
    sub_b = bus.subscribe()

    bus.publish("shared", n=1)

    assert (await anext(sub_a)).data == {"n": 1}
    assert (await anext(sub_b)).data == {"n": 1}


async def test_concurrent_publishers_and_subscribers_all_see_every_event() -> None:
    bus = EventBus()
    subscriber_count = 5
    publisher_count = 20

    async def collect(subscription: object, expected: int) -> list[int]:
        received = []
        async for event in subscription:  # type: ignore[attr-defined]
            received.append(event.data["n"])
            if len(received) == expected:
                return received
        return received

    subscriptions = [bus.subscribe() for _ in range(subscriber_count)]  # registers eagerly
    collectors = [
        asyncio.ensure_future(collect(sub, publisher_count)) for sub in subscriptions
    ]

    async def publish(n: int) -> None:
        await asyncio.sleep(0)
        bus.publish("tick", n=n)

    await asyncio.gather(*(publish(n) for n in range(publisher_count)))
    results = await asyncio.wait_for(asyncio.gather(*collectors), timeout=5)

    expected = set(range(publisher_count))
    for received in results:
        assert set(received) == expected
