"""On-chain metrics API endpoints — scores, metrics, and feed status."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ctrade.api.schemas.onchain import (
    OnChainAllScoresResponse,
    OnChainFeedStatusResponse,
    OnChainMetricResponse,
    OnChainMetricsResponse,
    OnChainScoreResponse,
)
from ctrade.feeds.onchain import OnChainFeed

router = APIRouter(prefix="/onchain", tags=["onchain"])


@router.get("/scores", response_model=OnChainAllScoresResponse)
async def get_all_scores() -> OnChainAllScoresResponse:
    """Get on-chain scores for all tracked assets."""
    feed = OnChainFeed.get_instance()
    scores = feed.get_all_scores()
    return OnChainAllScoresResponse(
        scores=scores,
        assets_tracked=len(scores),
    )


@router.get("/{symbol}/score", response_model=OnChainScoreResponse)
async def get_score(symbol: str) -> OnChainScoreResponse:
    """Get on-chain score for a specific asset."""
    feed = OnChainFeed.get_instance()
    factors = feed.get_contributing_factors(f"{symbol}/USDT")
    return OnChainScoreResponse(
        symbol=symbol.upper(),
        score=factors.get("score", 0.5),
        signal=factors.get("signal", "neutral"),
        metrics_count=factors.get("metrics_count", 0),
    )


@router.get("/{symbol}/metrics", response_model=OnChainMetricsResponse)
async def get_metrics(
    symbol: str,
    limit: int = Query(20, ge=1, le=100),
) -> OnChainMetricsResponse:
    """Get recent on-chain metrics for an asset."""
    feed = OnChainFeed.get_instance()
    data = feed.get_metrics(symbol.upper(), limit=limit)
    return OnChainMetricsResponse(
        symbol=symbol.upper(),
        metrics=[OnChainMetricResponse(**m) for m in data],
    )


@router.get("/status", response_model=OnChainFeedStatusResponse)
async def get_status() -> OnChainFeedStatusResponse:
    """Get on-chain feed health status."""
    feed = OnChainFeed.get_instance()
    status = feed.get_status()
    return OnChainFeedStatusResponse(**status)
