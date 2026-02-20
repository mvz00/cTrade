"""Tests for core domain models."""

from decimal import Decimal

from ctrade.core.enums import SignalAction, TradingMode, OrderSide
from ctrade.core.models import Candle, Signal, Order


def test_signal_defaults():
    """Signal should have sensible defaults."""
    signal = Signal()
    assert signal.action == SignalAction.HOLD
    assert signal.confidence == 0.0
    assert signal.contributing_factors == {}


def test_signal_with_values(sample_signal: Signal):
    """Signal should preserve provided values."""
    assert sample_signal.action == SignalAction.BUY
    assert sample_signal.confidence == 0.82
    assert sample_signal.technical_score == 0.85
    assert sample_signal.pair_symbol == "BTC/USDT"
    assert "rsi" in sample_signal.contributing_factors


def test_candle_immutability(sample_candle: Candle):
    """Candles should be frozen dataclasses."""
    import pytest

    with pytest.raises(AttributeError):
        sample_candle.close = Decimal("99999")  # type: ignore[misc]


def test_order_is_mutable(sample_order: Order):
    """Orders should be mutable (status changes during lifecycle)."""
    sample_order.status = "filled"
    assert sample_order.status == "filled"
    sample_order.filled_quantity = Decimal("0.01")
    assert sample_order.filled_quantity == Decimal("0.01")
