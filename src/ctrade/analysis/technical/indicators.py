"""Technical indicator computations using pandas-ta.

Each function takes a pandas DataFrame with OHLCV columns and returns
a normalized score between 0 and 1, where:
- 0.0 = strongly bearish signal
- 0.5 = neutral
- 1.0 = strongly bullish signal
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_rsi(
    df: pd.DataFrame, period: int = 14
) -> dict[str, Any]:
    """Compute RSI and return normalized score.

    Score mapping: RSI < 30 (oversold) → bullish (0.7-1.0)
                   RSI > 70 (overbought) → bearish (0.0-0.3)
                   RSI 30-70 → neutral (0.3-0.7)
    """
    try:
        import pandas_ta as ta
        rsi_series = ta.rsi(df["close"], length=period)
    except ImportError:
        # Fallback manual RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + rs))

    if rsi_series is None or rsi_series.empty:
        return {"value": 50.0, "score": 0.5, "signal": "neutral"}

    rsi_val = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0

    # Normalize to 0-1 score (inverted: low RSI = bullish = high score)
    if rsi_val <= 30:
        score = 0.7 + (30 - rsi_val) / 30 * 0.3
        signal = "oversold"
    elif rsi_val >= 70:
        score = 0.3 - (rsi_val - 70) / 30 * 0.3
        signal = "overbought"
    else:
        score = 0.3 + (70 - rsi_val) / 40 * 0.4
        signal = "neutral"

    return {"value": round(rsi_val, 2), "score": round(max(0, min(1, score)), 4), "signal": signal}


def compute_macd(
    df: pd.DataFrame, fast: int = 12, slow: int = 26, signal_period: int = 9
) -> dict[str, Any]:
    """Compute MACD and return normalized score.

    Score: histogram positive & rising → bullish
           histogram negative & falling → bearish
    """
    try:
        import pandas_ta as ta
        macd_df = ta.macd(df["close"], fast=fast, slow=slow, signal=signal_period)
        if macd_df is None or macd_df.empty:
            return {"value": 0.0, "histogram": 0.0, "score": 0.5, "signal": "neutral"}

        cols = macd_df.columns
        macd_line = macd_df[cols[0]].iloc[-1]
        signal_line = macd_df[cols[1]].iloc[-1]
        histogram = macd_df[cols[2]].iloc[-1]
        prev_histogram = macd_df[cols[2]].iloc[-2] if len(macd_df) > 1 else 0
    except (ImportError, Exception):
        ema_fast = df["close"].ewm(span=fast).mean()
        ema_slow = df["close"].ewm(span=slow).mean()
        macd_line_s = ema_fast - ema_slow
        signal_s = macd_line_s.ewm(span=signal_period).mean()
        hist_s = macd_line_s - signal_s

        macd_line = float(macd_line_s.iloc[-1])
        signal_line = float(signal_s.iloc[-1])
        histogram = float(hist_s.iloc[-1])
        prev_histogram = float(hist_s.iloc[-2]) if len(hist_s) > 1 else 0

    if pd.isna(macd_line) or pd.isna(histogram):
        return {"value": 0.0, "histogram": 0.0, "score": 0.5, "signal": "neutral"}

    macd_val = float(macd_line)
    hist_val = float(histogram)
    prev_hist = float(prev_histogram) if not pd.isna(prev_histogram) else 0.0

    # Score based on histogram direction and crossover
    if hist_val > 0 and hist_val > prev_hist:
        score = 0.7 + min(0.3, abs(hist_val) / (abs(macd_val) + 1e-8) * 0.3)
        signal = "bullish_momentum"
    elif hist_val > 0:
        score = 0.55
        signal = "bullish"
    elif hist_val < 0 and hist_val < prev_hist:
        score = 0.3 - min(0.3, abs(hist_val) / (abs(macd_val) + 1e-8) * 0.3)
        signal = "bearish_momentum"
    elif hist_val < 0:
        score = 0.45
        signal = "bearish"
    else:
        score = 0.5
        signal = "neutral"

    # Crossover bonus
    if prev_hist < 0 < hist_val:
        score = min(1.0, score + 0.15)
        signal = "bullish_crossover"
    elif prev_hist > 0 > hist_val:
        score = max(0.0, score - 0.15)
        signal = "bearish_crossover"

    return {
        "value": round(macd_val, 4),
        "histogram": round(hist_val, 4),
        "score": round(max(0, min(1, score)), 4),
        "signal": signal,
    }


def compute_bollinger_bands(
    df: pd.DataFrame, period: int = 20, std_dev: float = 2.0
) -> dict[str, Any]:
    """Compute Bollinger Bands and return normalized score.

    Score: price near lower band → bullish (potential bounce)
           price near upper band → bearish (potential reversal)
    """
    try:
        import pandas_ta as ta
        bb = ta.bbands(df["close"], length=period, std=std_dev)
        if bb is None or bb.empty:
            return {"upper": 0, "middle": 0, "lower": 0, "score": 0.5, "signal": "neutral"}
        cols = bb.columns
        upper = float(bb[cols[0]].iloc[-1])
        middle = float(bb[cols[1]].iloc[-1])
        lower = float(bb[cols[2]].iloc[-1])
    except (ImportError, Exception):
        sma = df["close"].rolling(window=period).mean()
        std = df["close"].rolling(window=period).std()
        upper = float((sma + std_dev * std).iloc[-1])
        middle = float(sma.iloc[-1])
        lower = float((sma - std_dev * std).iloc[-1])

    if pd.isna(upper) or pd.isna(lower) or upper == lower:
        return {"upper": 0, "middle": 0, "lower": 0, "score": 0.5, "signal": "neutral"}

    price = float(df["close"].iloc[-1])
    band_width = upper - lower

    # Position within bands (0=lower, 1=upper)
    position = (price - lower) / band_width if band_width > 0 else 0.5

    # Score: near lower band = bullish (buy zone), near upper = bearish (sell zone)
    score = 1.0 - position  # Invert: low position = high score

    if position < 0.2:
        signal = "near_lower"
    elif position > 0.8:
        signal = "near_upper"
    else:
        signal = "mid_band"

    return {
        "upper": round(upper, 4),
        "middle": round(middle, 4),
        "lower": round(lower, 4),
        "percent_b": round(position, 4),
        "score": round(max(0, min(1, score)), 4),
        "signal": signal,
    }


def compute_ema_cross(
    df: pd.DataFrame, short_period: int = 9, long_period: int = 21
) -> dict[str, Any]:
    """Compute EMA crossover and return normalized score.

    Score: short EMA above long EMA → bullish
           short EMA below long EMA → bearish
           Recent crossover → stronger signal
    """
    try:
        import pandas_ta as ta
        ema_short = ta.ema(df["close"], length=short_period)
        ema_long = ta.ema(df["close"], length=long_period)
    except ImportError:
        ema_short = df["close"].ewm(span=short_period).mean()
        ema_long = df["close"].ewm(span=long_period).mean()

    if ema_short is None or ema_long is None or ema_short.empty or ema_long.empty:
        return {"short_ema": 0, "long_ema": 0, "score": 0.5, "signal": "neutral"}

    short_val = float(ema_short.iloc[-1])
    long_val = float(ema_long.iloc[-1])
    prev_short = float(ema_short.iloc[-2]) if len(ema_short) > 1 else short_val
    prev_long = float(ema_long.iloc[-2]) if len(ema_long) > 1 else long_val

    if pd.isna(short_val) or pd.isna(long_val):
        return {"short_ema": 0, "long_ema": 0, "score": 0.5, "signal": "neutral"}

    # Distance between EMAs relative to price
    distance = (short_val - long_val) / long_val if long_val != 0 else 0

    # Base score from EMA relationship
    score = 0.5 + distance * 10  # Scale up the distance

    # Crossover detection
    if prev_short <= prev_long and short_val > long_val:
        score = min(1.0, score + 0.2)
        signal = "golden_cross"
    elif prev_short >= prev_long and short_val < long_val:
        score = max(0.0, score - 0.2)
        signal = "death_cross"
    elif short_val > long_val:
        signal = "bullish_trend"
    else:
        signal = "bearish_trend"

    return {
        "short_ema": round(short_val, 4),
        "long_ema": round(long_val, 4),
        "score": round(max(0, min(1, score)), 4),
        "signal": signal,
    }


def compute_all_indicators(
    df: pd.DataFrame,
    rsi_period: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bb_period: int = 20,
    bb_std: float = 2.0,
    ema_short: int = 9,
    ema_long: int = 21,
) -> dict[str, dict[str, Any]]:
    """Compute all indicators and return results dict."""
    return {
        "rsi": compute_rsi(df, rsi_period),
        "macd": compute_macd(df, macd_fast, macd_slow, macd_signal),
        "bollinger_bands": compute_bollinger_bands(df, bb_period, bb_std),
        "ema_cross": compute_ema_cross(df, ema_short, ema_long),
    }
