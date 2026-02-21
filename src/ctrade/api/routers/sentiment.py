"""Sentiment API endpoints — scores, timelines, and feed status."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ctrade.api.schemas.sentiment import (
    SentimentAllScoresResponse,
    SentimentContributingFactors,
    SentimentDataPointResponse,
    SentimentFeedStatusResponse,
    SentimentScoreResponse,
    SentimentTimelineResponse,
)
from ctrade.feeds.sentiment import SentimentFeed

router = APIRouter(prefix="/sentiment", tags=["sentiment"])


@router.get("/scores", response_model=SentimentAllScoresResponse)
async def get_all_scores() -> SentimentAllScoresResponse:
    """Get sentiment scores for all tracked assets."""
    feed = SentimentFeed.get_instance()
    scores = feed.get_all_scores()
    return SentimentAllScoresResponse(
        scores=scores,
        assets_tracked=len(scores),
    )


@router.get("/{symbol}/score", response_model=SentimentScoreResponse)
async def get_score(symbol: str) -> SentimentScoreResponse:
    """Get sentiment score for a specific asset (e.g. BTC, ETH)."""
    feed = SentimentFeed.get_instance()
    factors = feed.get_contributing_factors(f"{symbol}/USDT")
    return SentimentScoreResponse(
        symbol=symbol.upper(),
        score=factors.get("score", 0.5),
        signal=factors.get("signal", "neutral"),
        data_points=factors.get("data_points", 0),
    )


@router.get("/{symbol}/timeline", response_model=SentimentTimelineResponse)
async def get_timeline(
    symbol: str,
    limit: int = Query(20, ge=1, le=100),
) -> SentimentTimelineResponse:
    """Get recent sentiment data points for timeline display."""
    feed = SentimentFeed.get_instance()
    data = feed.get_recent_data(symbol.upper(), limit=limit)
    return SentimentTimelineResponse(
        symbol=symbol.upper(),
        data_points=[SentimentDataPointResponse(**dp) for dp in data],
    )


@router.get("/{symbol}/factors", response_model=SentimentContributingFactors)
async def get_factors(symbol: str) -> SentimentContributingFactors:
    """Get detailed contributing factors breakdown for an asset."""
    feed = SentimentFeed.get_instance()
    factors = feed.get_contributing_factors(f"{symbol}/USDT")
    return SentimentContributingFactors(**factors)


@router.get("/status", response_model=SentimentFeedStatusResponse)
async def get_status() -> SentimentFeedStatusResponse:
    """Get sentiment feed health status."""
    feed = SentimentFeed.get_instance()
    status = feed.get_status()
    return SentimentFeedStatusResponse(**status)
