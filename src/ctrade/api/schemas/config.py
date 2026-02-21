"""Pydantic request/response schemas for configuration endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---- Trading Mode ----

class TradingModeUpdate(BaseModel):
    mode: Literal["paper", "live"] | None = None
    max_order_usdt: float | None = Field(None, gt=0, le=100_000)
    max_open_positions: int | None = Field(None, ge=1, le=50)


class TradingModeResponse(BaseModel):
    mode: str
    max_order_usdt: float = 100.0
    max_open_positions: int = 5


# ---- Strategy ----

class StrategyConfigUpdate(BaseModel):
    active_strategy: str | None = None
    technical_weight: float | None = Field(None, ge=0, le=1)
    sentiment_weight: float | None = Field(None, ge=0, le=1)
    onchain_weight: float | None = Field(None, ge=0, le=1)
    entry_confidence_threshold: float | None = Field(None, ge=0, le=1)
    exit_confidence_threshold: float | None = Field(None, ge=0, le=1)


class StrategyConfigResponse(BaseModel):
    active_strategy: str
    technical_weight: float
    sentiment_weight: float
    onchain_weight: float
    entry_confidence_threshold: float
    exit_confidence_threshold: float


# ---- Risk ----

class RiskConfigUpdate(BaseModel):
    max_position_pct: float | None = Field(None, gt=0, le=1)
    max_daily_loss_pct: float | None = Field(None, gt=0, le=1)
    max_drawdown_pct: float | None = Field(None, gt=0, le=1)
    default_stop_loss_pct: float | None = Field(None, gt=0, le=0.5)
    default_take_profit_pct: float | None = Field(None, gt=0, le=1)


class RiskConfigResponse(BaseModel):
    max_position_pct: float
    max_daily_loss_pct: float
    max_drawdown_pct: float
    default_stop_loss_pct: float
    default_take_profit_pct: float


# ---- Exchange ----

class ExchangeAddRequest(BaseModel):
    name: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)
    passphrase: str | None = None


class ExchangeResponse(BaseModel):
    id: str
    name: str
    exchange_type: str
    is_active: bool
    created_at: str


class ExchangeTestResponse(BaseModel):
    success: bool
    message: str


class AvailableExchangeResponse(BaseModel):
    name: str
    exchange_type: str
    default_fee_pct: float
    supports_websocket: bool
