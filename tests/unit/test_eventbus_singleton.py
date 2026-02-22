"""Tests for EventBus singleton and new event types."""

from __future__ import annotations

import pytest

from ctrade.core.events import Event, EventBus, EventTypes


@pytest.fixture(autouse=True)
def reset_bus():
    """Reset singleton between tests."""
    EventBus.reset()
    yield
    EventBus.reset()


class TestEventBusSingleton:
    def test_get_instance_returns_same_object(self):
        a = EventBus.get_instance()
        b = EventBus.get_instance()
        assert a is b

    def test_reset_creates_new_instance(self):
        a = EventBus.get_instance()
        EventBus.reset()
        b = EventBus.get_instance()
        assert a is not b

    def test_get_instance_is_eventbus(self):
        bus = EventBus.get_instance()
        assert isinstance(bus, EventBus)


class TestAlertTriggeredEventType:
    def test_alert_triggered_constant_exists(self):
        assert hasattr(EventTypes, "ALERT_TRIGGERED")
        assert EventTypes.ALERT_TRIGGERED == "alert.triggered"

    def test_can_create_alert_event(self):
        event = Event(
            event_type=EventTypes.ALERT_TRIGGERED,
            data={"alert": {"id": "123"}, "pair": "BTC/USDT"},
        )
        assert event.event_type == "alert.triggered"
        assert event.data["pair"] == "BTC/USDT"


class TestEventBusPublishNowait:
    def test_publish_nowait_does_not_raise(self):
        bus = EventBus.get_instance()
        event = Event(event_type=EventTypes.SIGNAL_GENERATED, data={"pair": "ETH/USDT"})
        # Should not raise even though bus is not started
        bus.publish_nowait(event)
