"""Tests for the alert manager."""

from __future__ import annotations

import pytest

from ctrade.notifications.alert_manager import AlertManager


@pytest.fixture(autouse=True)
def _reset():
    AlertManager.reset()
    yield
    AlertManager.reset()


class TestAlertManagerInit:
    def test_singleton(self):
        a1 = AlertManager.get_instance()
        a2 = AlertManager.get_instance()
        assert a1 is a2

    def test_empty_initially(self):
        am = AlertManager.get_instance()
        assert am.list_alerts() == []
        assert am.get_history() == []


class TestCreateAlert:
    def test_create_price_alert(self):
        am = AlertManager.get_instance()
        alert = am.create_alert("price_above", "BTC/USDT", 70000.0, "BTC moon")
        assert alert["alert_type"] == "price_above"
        assert alert["symbol"] == "BTC/USDT"
        assert alert["value"] == 70000.0
        assert alert["is_active"] is True
        assert alert["message"] == "BTC moon"

    def test_list_alerts(self):
        am = AlertManager.get_instance()
        am.create_alert("price_above", "BTC/USDT", 70000.0)
        am.create_alert("price_below", "ETH/USDT", 3000.0)
        alerts = am.list_alerts()
        assert len(alerts) == 2


class TestDeleteAlert:
    def test_delete_existing(self):
        am = AlertManager.get_instance()
        alert = am.create_alert("price_above", "BTC/USDT", 70000.0)
        result = am.delete_alert(alert["id"])
        assert result is True
        assert len(am.list_alerts()) == 0

    def test_delete_nonexistent(self):
        am = AlertManager.get_instance()
        result = am.delete_alert("fake-id")
        assert result is False


class TestToggleAlert:
    def test_toggle_off(self):
        am = AlertManager.get_instance()
        alert = am.create_alert("price_above", "BTC/USDT", 70000.0)
        toggled = am.toggle_alert(alert["id"])
        assert toggled is not None
        assert toggled["is_active"] is False

    def test_toggle_on(self):
        am = AlertManager.get_instance()
        alert = am.create_alert("price_above", "BTC/USDT", 70000.0)
        am.toggle_alert(alert["id"])  # Off
        toggled = am.toggle_alert(alert["id"])  # On
        assert toggled is not None
        assert toggled["is_active"] is True

    def test_toggle_nonexistent(self):
        am = AlertManager.get_instance()
        result = am.toggle_alert("fake-id")
        assert result is None


class TestPriceAlerts:
    def test_price_above_triggers(self):
        am = AlertManager.get_instance()
        am.create_alert("price_above", "BTC/USDT", 70000.0)
        triggered = am.check_price("BTC/USDT", 71000.0)
        assert len(triggered) == 1
        assert triggered[0]["alert_type"] == "price_above"

    def test_price_above_no_trigger(self):
        am = AlertManager.get_instance()
        am.create_alert("price_above", "BTC/USDT", 70000.0)
        triggered = am.check_price("BTC/USDT", 69000.0)
        assert len(triggered) == 0

    def test_price_below_triggers(self):
        am = AlertManager.get_instance()
        am.create_alert("price_below", "BTC/USDT", 60000.0)
        triggered = am.check_price("BTC/USDT", 59000.0)
        assert len(triggered) == 1

    def test_one_shot_deactivation(self):
        am = AlertManager.get_instance()
        am.create_alert("price_above", "BTC/USDT", 70000.0)
        am.check_price("BTC/USDT", 71000.0)
        # Should not trigger again
        triggered = am.check_price("BTC/USDT", 72000.0)
        assert len(triggered) == 0

    def test_wrong_symbol_no_trigger(self):
        am = AlertManager.get_instance()
        am.create_alert("price_above", "BTC/USDT", 70000.0)
        triggered = am.check_price("ETH/USDT", 71000.0)
        assert len(triggered) == 0


class TestSignalAlerts:
    def test_signal_buy_triggers(self):
        am = AlertManager.get_instance()
        am.create_alert("signal_buy", "BTC/USDT", 0.7)
        triggered = am.check_signal("BTC/USDT", "BUY")
        assert len(triggered) == 1

    def test_signal_sell_triggers(self):
        am = AlertManager.get_instance()
        am.create_alert("signal_sell", "BTC/USDT", 0.7)
        triggered = am.check_signal("BTC/USDT", "SELL")
        assert len(triggered) == 1

    def test_signal_buy_no_trigger_on_sell(self):
        am = AlertManager.get_instance()
        am.create_alert("signal_buy", "BTC/USDT", 0.7)
        triggered = am.check_signal("BTC/USDT", "SELL")
        assert len(triggered) == 0


class TestAlertHistory:
    def test_history_populated_after_trigger(self):
        am = AlertManager.get_instance()
        am.create_alert("price_above", "BTC/USDT", 70000.0)
        am.check_price("BTC/USDT", 71000.0)
        history = am.get_history()
        assert len(history) == 1
        assert history[0]["triggered_value"] == 71000.0

    def test_history_limit(self):
        am = AlertManager.get_instance()
        for i in range(10):
            am.create_alert("price_above", "BTC/USDT", float(i))
            am.check_price("BTC/USDT", float(i + 1))
        history = am.get_history(limit=5)
        assert len(history) == 5
