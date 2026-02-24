"""Technical analysis engine — produces composite scores and trading signals."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pandas as pd

from ctrade.analysis.technical.indicators import compute_all_indicators
from ctrade.core.enums import SignalAction
from ctrade.core.models import Candle, Signal

logger = logging.getLogger(__name__)


class TechnicalAnalysisEngine:
    """Computes technical indicators and generates trading signals."""

    def analyze(
        self,
        candles: list[Candle],
        entry_threshold: float = 0.55,
        exit_threshold: float = 0.45,
        rsi_period: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        bb_period: int = 20,
        bb_std: float = 2.0,
    ) -> tuple[Signal, dict[str, Any]]:
        """Analyze candles and produce a signal with indicator details.

        Returns:
            Tuple of (Signal, indicators_dict)
        """
        if len(candles) < 30:
            # Not enough data
            return (
                Signal(
                    id=uuid4(),
                    pair_symbol=candles[0].pair_symbol if candles else "",
                    action=SignalAction.HOLD,
                    confidence=0.0,
                    strategy_name="technical",
                ),
                {},
            )

        df = self._candles_to_df(candles)
        symbol = candles[-1].pair_symbol

        indicators = compute_all_indicators(
            df,
            rsi_period=rsi_period,
            macd_fast=macd_fast,
            macd_slow=macd_slow,
            macd_signal=macd_signal,
            bb_period=bb_period,
            bb_std=bb_std,
        )

        # Weighted composite score
        weights = {
            "rsi": 0.30,
            "macd": 0.30,
            "bollinger_bands": 0.20,
            "ema_cross": 0.20,
        }

        composite = sum(
            indicators[name]["score"] * weight
            for name, weight in weights.items()
            if name in indicators
        )

        # Determine action
        if composite >= entry_threshold:
            action = SignalAction.BUY
        elif composite <= exit_threshold:
            action = SignalAction.SELL
        else:
            action = SignalAction.HOLD

        signal = Signal(
            id=uuid4(),
            pair_symbol=symbol,
            action=action,
            confidence=round(composite, 4),
            technical_score=round(composite, 4),
            strategy_name="technical",
            contributing_factors={
                name: {"score": ind["score"], "signal": ind["signal"]}
                for name, ind in indicators.items()
            },
        )

        return signal, indicators

    @staticmethod
    def _candles_to_df(candles: list[Candle]) -> pd.DataFrame:
        """Convert candle list to pandas DataFrame."""
        data = {
            "time": [c.time for c in candles],
            "open": [float(c.open) for c in candles],
            "high": [float(c.high) for c in candles],
            "low": [float(c.low) for c in candles],
            "close": [float(c.close) for c in candles],
            "volume": [float(c.volume) for c in candles],
        }
        df = pd.DataFrame(data)
        df.set_index("time", inplace=True)
        return df
