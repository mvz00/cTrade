"""Recommendation engine — ranks coins by buy potential for the dashboard.

Uses already-cached CoinMarketCap data (no new API calls) to score and
rank coins based on the active strategy mode (quicktrade vs long_only).
Each recommendation includes an estimated trade duration.
"""

from __future__ import annotations

import math
from typing import Any


# Stablecoins to exclude from recommendations
_STABLECOINS = frozenset({
    "USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD", "USDD",
    "PYUSD", "GUSD", "USDP", "FRAX", "LUSD", "CRVUSD", "GHO",
    "EURC", "AEUR",
})

_MIN_MARKET_CAP = 10_000_000  # $10M minimum


def _pct_to_score(pct_change: float, scale: float) -> float:
    """Convert a percent change to a 0-1 score using a sigmoid.

    Same formula as ``CoinMarketCapFeed._pct_to_score``.
    """
    return 1.0 / (1.0 + math.exp(-pct_change / scale))


def _volume_score(volume_24h: float, all_volumes: list[float]) -> float:
    """Score a coin's volume relative to the median of all listings."""
    if not all_volumes:
        return 0.5
    median_vol = all_volumes[len(all_volumes) // 2]
    if median_vol <= 0:
        return 0.5
    ratio = volume_24h / median_vol
    return 1.0 / (1.0 + math.exp(-math.log(max(ratio, 0.01)) / 2.0))


def estimate_trade_time(
    strategy_mode: str,
    pct_change_1h: float,
    pct_change_24h: float,
    take_profit_pct: float,
) -> str:
    """Estimate how long a trade should be held before TP is reached.

    Returns a human-readable string like "~30m", "~2h", "~1d".
    """
    if strategy_mode == "quicktrade":
        # Use 1h price velocity to estimate time to take-profit
        hourly_velocity = max(abs(pct_change_1h), 0.1)
        hours = (take_profit_pct * 100) / hourly_velocity
        # Clamp to 15min – 4h
        hours = max(0.25, min(hours, 4.0))
    else:
        # Long mode: use 24h trend velocity
        hourly_velocity = max(abs(pct_change_24h) / 24.0, 0.01)
        hours = (take_profit_pct * 100) / hourly_velocity
        # Clamp to 1h – 7d
        hours = max(1.0, min(hours, 168.0))

    return _format_hours(hours)


def _format_hours(hours: float) -> str:
    """Convert hours to a human-readable duration string."""
    if hours < 1.0:
        minutes = round(hours * 60)
        return f"~{minutes}m"
    elif hours < 24.0:
        h = round(hours)
        return f"~{h}h"
    else:
        days = round(hours / 24.0)
        return f"~{days}d"


def compute_recommendations(
    strategy_mode: str,
    quote_currency: str,
    risk_config: dict[str, Any],
    strategy_config: dict[str, Any],
) -> dict[str, Any]:
    """Compute top 10 recommended buys based on strategy mode.

    Returns a dict with ``strategy_mode``, ``recommendations``, and ``source``.
    """
    from ctrade.feeds.coinmarketcap import CoinMarketCapFeed

    cmc = CoinMarketCapFeed.get_instance()

    if not cmc.is_enabled or not cmc._listings:
        return {
            "strategy_mode": strategy_mode,
            "recommendations": [],
            "source": "unavailable",
        }

    take_profit_pct = risk_config.get("default_take_profit_pct", 0.06)
    entry_threshold = strategy_config.get("entry_confidence_threshold", 0.55)

    # Pre-compute sorted volumes for volume scoring
    all_volumes = sorted(
        item.volume_24h for item in cmc._listings if item.volume_24h > 0
    )

    scored: list[dict[str, Any]] = []

    for listing in cmc._listings:
        # Filter stablecoins and low market cap
        if listing.symbol in _STABLECOINS:
            continue
        if listing.market_cap < _MIN_MARKET_CAP:
            continue

        # Compute individual scores
        score_1h = _pct_to_score(listing.pct_change_1h, scale=5.0)
        score_24h = _pct_to_score(listing.pct_change_24h, scale=10.0)
        score_7d = _pct_to_score(listing.pct_change_7d, scale=20.0)
        vol_score = _volume_score(listing.volume_24h, all_volumes)

        # Momentum score from CMC feed
        momentum = cmc.get_momentum_score(f"{listing.symbol}/USDT")
        if momentum is None:
            momentum = 0.5

        # Strategy-mode-specific composite score
        if strategy_mode == "quicktrade":
            # Favor fast-moving, high-volume coins
            composite = (
                0.40 * _pct_to_score(abs(listing.pct_change_1h), scale=3.0)
                + 0.25 * vol_score
                + 0.20 * score_24h
                + 0.15 * momentum
            )
        else:
            # Long mode: favor sustained trend strength
            composite = (
                0.35 * score_7d
                + 0.25 * score_24h
                + 0.20 * momentum
                + 0.20 * vol_score
            )

        # Only include coins above the entry threshold
        if composite < entry_threshold:
            continue

        est_time = estimate_trade_time(
            strategy_mode,
            listing.pct_change_1h,
            listing.pct_change_24h,
            take_profit_pct,
        )

        scored.append({
            "symbol": listing.symbol,
            "name": listing.name,
            "pair": f"{listing.symbol}/{quote_currency}",
            "score": round(composite, 4),
            "pct_change_1h": listing.pct_change_1h,
            "pct_change_24h": listing.pct_change_24h,
            "pct_change_7d": listing.pct_change_7d,
            "volume_24h": listing.volume_24h,
            "market_cap": listing.market_cap,
            "est_trade_time": est_time,
        })

    # Sort by score descending, take top 10
    scored.sort(key=lambda x: x["score"], reverse=True)
    top_10 = scored[:10]

    # Add rank
    for i, item in enumerate(top_10, 1):
        item["rank"] = i

    return {
        "strategy_mode": strategy_mode,
        "recommendations": top_10,
        "source": "coinmarketcap",
    }
