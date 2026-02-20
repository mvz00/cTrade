"""Tests for the event bus."""

import asyncio

import pytest

from ctrade.core.events import Event, EventBus, EventTypes


@pytest.mark.asyncio
async def test_event_bus_publish_subscribe():
    """Event bus should deliver events to subscribed handlers."""
    bus = EventBus()
    received_events: list[Event] = []

    async def handler(event: Event) -> None:
        received_events.append(event)

    bus.subscribe(EventTypes.CANDLE_UPDATE, handler)
    await bus.start()

    event = Event(event_type=EventTypes.CANDLE_UPDATE, data={"pair": "BTC/USDT"})
    await bus.publish(event)

    # Give the processing loop time to handle the event
    await asyncio.sleep(0.1)
    await bus.stop()

    assert len(received_events) == 1
    assert received_events[0].data["pair"] == "BTC/USDT"


@pytest.mark.asyncio
async def test_event_bus_multiple_handlers():
    """Multiple handlers should all receive the same event."""
    bus = EventBus()
    results: list[str] = []

    async def handler_a(event: Event) -> None:
        results.append("a")

    async def handler_b(event: Event) -> None:
        results.append("b")

    bus.subscribe("test.event", handler_a)
    bus.subscribe("test.event", handler_b)
    await bus.start()

    await bus.publish(Event(event_type="test.event"))
    await asyncio.sleep(0.1)
    await bus.stop()

    assert sorted(results) == ["a", "b"]


@pytest.mark.asyncio
async def test_event_bus_handler_error_isolation():
    """A failing handler should not prevent other handlers from running."""
    bus = EventBus()
    results: list[str] = []

    async def failing_handler(event: Event) -> None:
        raise ValueError("intentional test error")

    async def good_handler(event: Event) -> None:
        results.append("ok")

    bus.subscribe("test.event", failing_handler)
    bus.subscribe("test.event", good_handler)
    await bus.start()

    await bus.publish(Event(event_type="test.event"))
    await asyncio.sleep(0.1)
    await bus.stop()

    assert results == ["ok"]


@pytest.mark.asyncio
async def test_event_bus_unsubscribe():
    """Unsubscribed handlers should not receive events."""
    bus = EventBus()
    results: list[str] = []

    async def handler(event: Event) -> None:
        results.append("received")

    bus.subscribe("test.event", handler)
    bus.unsubscribe("test.event", handler)
    await bus.start()

    await bus.publish(Event(event_type="test.event"))
    await asyncio.sleep(0.1)
    await bus.stop()

    assert results == []
