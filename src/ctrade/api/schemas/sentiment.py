"""Pydantic schemas for sentiment API endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class SentimentScoreResponse(BaseModel):
    """Sentiment score for a single asset."""

    symbol: str
    score: float
    signal: str  # bullish / bearish / neutral
    data_points: int


class SentimentAllScoresResponse(BaseModel):
    """Sentiment scores for all tracked assets."""

    scores: dict[str, float]
    assets_tracked: int


class SentimentDataPointResponse(BaseModel):
    """A single sentiment data point for timeline display."""

    source: str
    text: str
    label: str
    score: float
    model: str
    timestamp: str


class SentimentTimelineResponse(BaseModel):
    """Sentiment timeline for an asset."""

    symbol: str
    data_points: list[SentimentDataPointResponse]


class SentimentContributingFactors(BaseModel):
    """Detailed contributing factors breakdown."""

    score: float
    signal: str
    data_points: int
    sources: dict[str, float] | None = None
    source_counts: dict[str, int] | None = None


class SentimentFeedStatusResponse(BaseModel):
    """Sentiment feed health status."""

    enabled: bool
    healthy: bool
    last_fetch: str | None
    data_points: int
    assets_tracked: int
    classifier_model: str
    using_fallback: bool
