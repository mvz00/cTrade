"""Pydantic schemas for the market screener endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class ScreenerCoin(BaseModel):
    """Single coin entry in screener results."""

    symbol: str
    name: str
    cmc_rank: int
    market_cap: float
    volume_24h: float
    pct_change_1h: float
    pct_change_24h: float
    pct_change_7d: float
    volume_change_24h: float = 0
    momentum_score: float | None = None


class ScreenerResponse(BaseModel):
    """Wrapper for screener results."""

    coins: list[ScreenerCoin]
    last_updated: str | None = None
    source: str = "coinmarketcap"


class CMCFeedStatus(BaseModel):
    """Status of the CoinMarketCap data feed."""

    enabled: bool
    healthy: bool
    last_fetch: str | None = None
    listings_count: int = 0
