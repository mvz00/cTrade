"""Pydantic schemas for alert endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CreateAlertRequest(BaseModel):
    alert_type: Literal[
        "price_above", "price_below",
        "signal_buy", "signal_sell",
        "pnl_above", "pnl_below",
    ]
    symbol: str = Field(min_length=1)
    value: float = Field(description="Threshold value (price in USD, PnL in %)")
    message: str | None = None


class AlertConfigResponse(BaseModel):
    id: str
    alert_type: str
    symbol: str
    value: float
    message: str | None = None
    is_active: bool
    created_at: str


class AlertHistoryResponse(BaseModel):
    id: str
    alert_id: str
    alert_type: str
    symbol: str
    message: str
    triggered_value: float
    triggered_at: str
