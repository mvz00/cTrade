"""Pydantic schemas for the recommendations endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class RecommendedBuy(BaseModel):
    """Single coin recommendation."""

    rank: int
    symbol: str
    name: str
    pair: str
    score: float
    pct_change_1h: float
    pct_change_24h: float
    pct_change_7d: float
    volume_24h: float
    market_cap: float
    est_trade_time: str


class RecommendationsResponse(BaseModel):
    """Wrapper for recommendation results."""

    strategy_mode: str
    recommendations: list[RecommendedBuy]
    source: str = "coinmarketcap"
