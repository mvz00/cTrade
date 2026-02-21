"""Pydantic schemas for on-chain API endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class OnChainScoreResponse(BaseModel):
    """On-chain score for a single asset."""

    symbol: str
    score: float
    signal: str  # bullish / bearish / neutral
    metrics_count: int


class OnChainAllScoresResponse(BaseModel):
    """On-chain scores for all tracked assets."""

    scores: dict[str, float]
    assets_tracked: int


class OnChainMetricResponse(BaseModel):
    """A single on-chain metric data point."""

    metric_name: str
    metric_value: float
    source: str
    timestamp: str


class OnChainMetricsResponse(BaseModel):
    """On-chain metrics for an asset."""

    symbol: str
    metrics: list[OnChainMetricResponse]


class OnChainFeedStatusResponse(BaseModel):
    """On-chain feed health status."""

    enabled: bool
    healthy: bool
    last_fetch: str | None
    metrics_count: int
    assets_tracked: int
