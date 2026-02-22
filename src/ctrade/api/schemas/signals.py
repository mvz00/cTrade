"""Pydantic schemas for signal endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SignalResponse(BaseModel):
    id: str
    pair_symbol: str
    action: str
    confidence: float
    technical_score: float | None = None
    sentiment_score: float | None = None
    onchain_score: float | None = None
    derivatives_score: float | None = None
    market_sentiment_score: float | None = None
    cvd_score: float | None = None
    social_velocity_score: float | None = None
    strategy_name: str
    contributing_factors: dict[str, Any] = {}
    created_at: str


class IndicatorResponse(BaseModel):
    symbol: str
    indicators: dict[str, Any]
    timestamp: str
