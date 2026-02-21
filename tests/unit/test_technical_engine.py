"""Tests for the technical analysis engine and indicators."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from ctrade.analysis.technical.indicators import (
    compute_all_indicators,
    compute_bollinger_bands,
    compute_ema_cross,
    compute_macd,
    compute_rsi,
)
from ctrade.analysis.technical.engine import TechnicalAnalysisEngine
from ctrade.core.enums import Timeframe
from ctrade.core.models import Candle


def _make_ohlcv_df(prices: list[float], length: int = 100) -> pd.DataFrame:
    """Create a simple OHLCV DataFrame from close prices."""
    if len(prices) < length:
        # Extend with random walk from last price
        rng = np.random.RandomState(42)
        last = prices[-1] if prices else 100.0
        while len(prices) < length:
            last = last * (1 + rng.normal(0, 0.005))
            prices.append(last)
    df = pd.DataFrame({
        "open": prices,
        "high": [p * 1.005 for p in prices],
        "low": [p * 0.995 for p in prices],
        "close": prices,
        "volume": [1000.0] * len(prices),
    })
    return df


def _trending_up_df(length: int = 100) -> pd.DataFrame:
    """Create DataFrame with uptrending prices."""
    prices = [100.0 + i * 0.5 for i in range(length)]
    return _make_ohlcv_df(prices, length)


def _trending_down_df(length: int = 100) -> pd.DataFrame:
    """Create DataFrame with downtrending prices."""
    prices = [200.0 - i * 0.5 for i in range(length)]
    return _make_ohlcv_df(prices, length)


def _flat_df(length: int = 100) -> pd.DataFrame:
    """Create DataFrame with flat/sideways prices."""
    rng = np.random.RandomState(42)
    prices = [100.0 + rng.normal(0, 0.5) for _ in range(length)]
    return _make_ohlcv_df(prices, length)


def _make_candles(prices: list[float], symbol: str = "BTC/USDT") -> list[Candle]:
    """Create proper Candle objects from close prices."""
    now = datetime.now(timezone.utc)
    candles = []
    for i, price in enumerate(prices):
        candles.append(Candle(
            time=now - timedelta(hours=len(prices) - i),
            pair_symbol=symbol,
            timeframe=Timeframe.H1,
            open=Decimal(str(round(price, 4))),
            high=Decimal(str(round(price * 1.005, 4))),
            low=Decimal(str(round(price * 0.995, 4))),
            close=Decimal(str(round(price, 4))),
            volume=Decimal("1000"),
        ))
    return candles


class TestRSI:
    def test_returns_valid_structure(self):
        result = compute_rsi(_flat_df())
        assert "value" in result
        assert "score" in result
        assert "signal" in result

    def test_score_range(self):
        result = compute_rsi(_flat_df())
        assert 0.0 <= result["score"] <= 1.0

    def test_uptrend_higher_score(self):
        result = compute_rsi(_trending_up_df())
        # Uptrend -> RSI high -> overbought -> lower score
        assert result["score"] < 0.5

    def test_downtrend_lower_rsi(self):
        result = compute_rsi(_trending_down_df())
        # Downtrend -> RSI low -> oversold -> higher score (bullish)
        assert result["score"] > 0.5


class TestMACD:
    def test_returns_valid_structure(self):
        result = compute_macd(_flat_df())
        assert "value" in result
        assert "histogram" in result
        assert "score" in result
        assert "signal" in result

    def test_score_range(self):
        result = compute_macd(_flat_df())
        assert 0.0 <= result["score"] <= 1.0

    def test_uptrend_bullish(self):
        result = compute_macd(_trending_up_df())
        assert result["score"] >= 0.5

    def test_downtrend_bearish(self):
        result = compute_macd(_trending_down_df())
        assert result["score"] <= 0.5


class TestBollingerBands:
    def test_returns_valid_structure(self):
        result = compute_bollinger_bands(_flat_df())
        assert "upper" in result
        assert "middle" in result
        assert "lower" in result
        assert "score" in result

    def test_score_range(self):
        result = compute_bollinger_bands(_flat_df())
        assert 0.0 <= result["score"] <= 1.0

    def test_bands_have_valid_values(self):
        result = compute_bollinger_bands(_flat_df())
        # Just check they are nonzero (valid computation)
        assert result["upper"] > 0
        assert result["middle"] > 0
        assert result["lower"] > 0


class TestEMACross:
    def test_returns_valid_structure(self):
        result = compute_ema_cross(_flat_df())
        assert "short_ema" in result
        assert "long_ema" in result
        assert "score" in result
        assert "signal" in result

    def test_score_range(self):
        result = compute_ema_cross(_flat_df())
        assert 0.0 <= result["score"] <= 1.0

    def test_uptrend_bullish(self):
        result = compute_ema_cross(_trending_up_df())
        assert result["signal"] in ("bullish_trend", "golden_cross")


class TestAllIndicators:
    def test_returns_all_keys(self):
        result = compute_all_indicators(_flat_df())
        assert "rsi" in result
        assert "macd" in result
        assert "bollinger_bands" in result
        assert "ema_cross" in result

    def test_all_scores_in_range(self):
        result = compute_all_indicators(_flat_df())
        for name, indicator in result.items():
            assert 0.0 <= indicator["score"] <= 1.0, f"{name} score out of range"


class TestTechnicalAnalysisEngine:
    def test_analyze_returns_signal_and_indicators(self):
        rng = np.random.RandomState(42)
        prices = [100.0 + rng.normal(0, 2) for _ in range(100)]
        candles = _make_candles(prices)

        engine = TechnicalAnalysisEngine()
        signal, indicators = engine.analyze(candles)
        assert signal is not None
        assert signal.action in ("BUY", "SELL", "HOLD")
        assert 0 <= signal.confidence <= 1
        assert "rsi" in indicators

    def test_insufficient_data_returns_hold(self):
        prices = [100.0 + i * 0.1 for i in range(10)]
        candles = _make_candles(prices)

        engine = TechnicalAnalysisEngine()
        signal, indicators = engine.analyze(candles)
        assert signal.action == "HOLD"
        assert signal.confidence == 0.0
