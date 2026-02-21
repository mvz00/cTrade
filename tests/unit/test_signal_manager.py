"""Tests for the signal manager."""

from __future__ import annotations

from uuid import uuid4

import pytest

from ctrade.core.enums import SignalAction
from ctrade.core.models import Signal
from ctrade.strategy.signal_manager import SignalManager


@pytest.fixture(autouse=True)
def _reset():
    SignalManager.reset()
    yield
    SignalManager.reset()


def _make_signal(
    symbol: str = "BTC/USDT",
    action: str = "BUY",
    confidence: float = 0.8,
) -> Signal:
    return Signal(
        id=uuid4(),
        pair_symbol=symbol,
        action=SignalAction(action),
        confidence=confidence,
        technical_score=0.75,
        sentiment_score=None,
        onchain_score=None,
        contributing_factors={"rsi": {"score": 0.7}},
        strategy_name="test",
    )


class TestSignalManagerInit:
    def test_singleton(self):
        s1 = SignalManager.get_instance()
        s2 = SignalManager.get_instance()
        assert s1 is s2

    def test_empty_initially(self):
        sm = SignalManager.get_instance()
        assert sm.list_signals() == []


class TestAddSignal:
    def test_add_and_list(self):
        sm = SignalManager.get_instance()
        sig = _make_signal()
        sm.add_signal(sig)
        signals = sm.list_signals()
        assert len(signals) == 1
        assert signals[0]["pair_symbol"] == "BTC/USDT"

    def test_add_with_indicators(self):
        sm = SignalManager.get_instance()
        sig = _make_signal()
        indicators = {"rsi": {"value": 35, "score": 0.7}}
        sm.add_signal(sig, indicators)
        result = sm.get_indicators("BTC/USDT")
        assert result is not None
        assert "rsi" in result

    def test_max_signals_enforced(self):
        sm = SignalManager.get_instance()
        for i in range(600):
            sm.add_signal(_make_signal())
        # Should be capped
        assert len(sm.list_signals(limit=1000)) <= SignalManager.MAX_SIGNALS


class TestFilterSignals:
    def test_filter_by_symbol(self):
        sm = SignalManager.get_instance()
        sm.add_signal(_make_signal("BTC/USDT"))
        sm.add_signal(_make_signal("ETH/USDT"))
        btc = sm.list_signals(symbol="BTC/USDT")
        assert len(btc) == 1
        assert btc[0]["pair_symbol"] == "BTC/USDT"

    def test_filter_by_action(self):
        sm = SignalManager.get_instance()
        sm.add_signal(_make_signal(action="BUY"))
        sm.add_signal(_make_signal(action="SELL"))
        buys = sm.list_signals(action="BUY")
        assert len(buys) == 1
        assert buys[0]["action"] == "BUY"

    def test_limit(self):
        sm = SignalManager.get_instance()
        for _ in range(10):
            sm.add_signal(_make_signal())
        limited = sm.list_signals(limit=3)
        assert len(limited) == 3

    def test_get_latest(self):
        sm = SignalManager.get_instance()
        sm.add_signal(_make_signal("BTC/USDT", "HOLD", 0.5))
        sm.add_signal(_make_signal("BTC/USDT", "BUY", 0.9))
        latest = sm.get_latest("BTC/USDT")
        assert latest is not None
        assert latest["action"] == "BUY"
        assert latest["confidence"] == 0.9

    def test_get_latest_none(self):
        sm = SignalManager.get_instance()
        assert sm.get_latest("NONEXISTENT") is None


class TestIndicatorsCache:
    def test_no_indicators_initially(self):
        sm = SignalManager.get_instance()
        assert sm.get_indicators("BTC/USDT") is None

    def test_indicators_updated_per_symbol(self):
        sm = SignalManager.get_instance()
        sm.add_signal(
            _make_signal("BTC/USDT"),
            {"rsi": {"score": 0.8}},
        )
        sm.add_signal(
            _make_signal("ETH/USDT"),
            {"rsi": {"score": 0.3}},
        )
        btc_ind = sm.get_indicators("BTC/USDT")
        eth_ind = sm.get_indicators("ETH/USDT")
        assert btc_ind is not None
        assert eth_ind is not None
        assert btc_ind["rsi"]["score"] == 0.8
        assert eth_ind["rsi"]["score"] == 0.3
