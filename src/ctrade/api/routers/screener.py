"""Market screener API endpoints — top gainers, losers, and filtered listings."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from ctrade.api.schemas.screener import CMCFeedStatus, ScreenerCoin, ScreenerResponse
from ctrade.feeds.coinmarketcap import CoinMarketCapFeed

router = APIRouter(prefix="/screener", tags=["screener"])


@router.get("/gainers", response_model=ScreenerResponse)
async def top_gainers(
    limit: int = Query(20, ge=1, le=100),
) -> ScreenerResponse:
    """Get top gaining cryptocurrencies by 24h price change."""
    feed = CoinMarketCapFeed.get_instance()
    if not feed.is_enabled:
        return ScreenerResponse(coins=[], source="disabled")

    gainers = feed.get_top_gainers(limit=limit)
    return ScreenerResponse(
        coins=[ScreenerCoin(**g) for g in gainers],
        last_updated=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/losers", response_model=ScreenerResponse)
async def top_losers(
    limit: int = Query(20, ge=1, le=100),
) -> ScreenerResponse:
    """Get top losing cryptocurrencies by 24h price change."""
    feed = CoinMarketCapFeed.get_instance()
    if not feed.is_enabled:
        return ScreenerResponse(coins=[], source="disabled")

    losers = feed.get_top_losers(limit=limit)
    return ScreenerResponse(
        coins=[ScreenerCoin(**g) for g in losers],
        last_updated=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/search", response_model=ScreenerResponse)
async def screener_search(
    sort_by: str = Query("pct_change_24h"),
    sort_dir: str = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    min_market_cap: float = Query(0, ge=0),
    min_volume: float = Query(0, ge=0),
) -> ScreenerResponse:
    """Market screener: filter and sort cryptocurrencies."""
    feed = CoinMarketCapFeed.get_instance()
    if not feed.is_enabled:
        return ScreenerResponse(coins=[], source="disabled")

    results = feed.get_screener_data(
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        min_market_cap=min_market_cap,
        min_volume=min_volume,
    )
    return ScreenerResponse(
        coins=[ScreenerCoin(**r) for r in results],
        last_updated=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/momentum/{symbol:path}")
async def get_momentum(symbol: str) -> dict:
    """Get momentum score for a specific trading pair."""
    feed = CoinMarketCapFeed.get_instance()
    score = feed.get_momentum_score(symbol)
    base = symbol.split("/")[0]
    listing = feed.get_listing(base)
    return {
        "symbol": symbol,
        "momentum_score": score,
        "details": listing.to_dict() if listing else None,
        "source": "coinmarketcap" if feed.is_enabled else "disabled",
    }


@router.get("/status", response_model=CMCFeedStatus)
async def feed_status() -> CMCFeedStatus:
    """Get CoinMarketCap feed status."""
    feed = CoinMarketCapFeed.get_instance()
    return CMCFeedStatus(
        enabled=feed.is_enabled,
        healthy=feed._healthy,
        listings_count=len(feed._listings),
    )
