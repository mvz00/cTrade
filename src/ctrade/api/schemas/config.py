"""Pydantic request/response schemas for configuration endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---- Trading Mode ----

class TradingModeUpdate(BaseModel):
    mode: Literal["paper", "live"] | None = None
    max_order_usdt: float | None = Field(None, gt=0, le=100_000)
    max_open_positions: int | None = Field(None, ge=1, le=50)
    default_quote_currency: str | None = None
    order_timeout_seconds: int | None = Field(None, ge=5, le=600)


class TradingModeResponse(BaseModel):
    mode: str
    max_order_usdt: float = 100.0
    max_open_positions: int = 5
    default_quote_currency: str = "USDT"
    order_timeout_seconds: int = 60


# ---- Strategy ----

class StrategyConfigUpdate(BaseModel):
    active_strategy: str | None = None
    technical_weight: float | None = Field(None, ge=0, le=1)
    sentiment_weight: float | None = Field(None, ge=0, le=1)
    onchain_weight: float | None = Field(None, ge=0, le=1)
    derivatives_weight: float | None = Field(None, ge=0, le=1)
    market_sentiment_weight: float | None = Field(None, ge=0, le=1)
    cvd_weight: float | None = Field(None, ge=0, le=1)
    social_velocity_weight: float | None = Field(None, ge=0, le=1)
    screener_weight: float | None = Field(None, ge=0, le=1)
    screener_priority: int | None = Field(None, ge=0, le=100)
    intelligence_priority: int | None = Field(None, ge=0, le=100)
    signals_priority: int | None = Field(None, ge=0, le=100)
    strategy_mode: str | None = Field(None, pattern=r"^(long_only|quicktrade)$")
    quicktrade_min_1h_change_pct: float | None = Field(None, ge=0.5, le=20.0)
    risk_appetite: int | None = Field(None, ge=1, le=10)
    entry_confidence_threshold: float | None = Field(None, ge=0, le=1)
    exit_confidence_threshold: float | None = Field(None, ge=0, le=1)
    min_hold_minutes: int | None = Field(None, ge=0, le=120)


class StrategyConfigResponse(BaseModel):
    active_strategy: str
    technical_weight: float
    sentiment_weight: float
    onchain_weight: float
    derivatives_weight: float = 0.17
    market_sentiment_weight: float = 0.17
    cvd_weight: float = 0.10
    social_velocity_weight: float = 0.08
    screener_weight: float = 0.0
    screener_priority: int = 50
    intelligence_priority: int = 50
    signals_priority: int = 50
    strategy_mode: str = "long_only"
    quicktrade_min_1h_change_pct: float = 2.0
    risk_appetite: int = 5
    entry_confidence_threshold: float
    exit_confidence_threshold: float
    min_hold_minutes: int = 15


# ---- Risk ----

class RiskConfigUpdate(BaseModel):
    max_position_pct: float | None = Field(None, gt=0, le=1)
    max_daily_loss_pct: float | None = Field(None, gt=0, le=1)
    max_drawdown_pct: float | None = Field(None, gt=0, le=1)
    default_stop_loss_pct: float | None = Field(None, gt=0, le=0.5)
    default_take_profit_pct: float | None = Field(None, gt=0, le=1)
    sl_rebuy_delay_hours: float | None = Field(None, ge=0, le=72)


class RiskConfigResponse(BaseModel):
    max_position_pct: float
    max_daily_loss_pct: float
    max_drawdown_pct: float
    default_stop_loss_pct: float
    default_take_profit_pct: float
    sl_rebuy_delay_hours: float = 1.0


# ---- Email Notifications ----

class EmailConfigUpdate(BaseModel):
    enabled: bool | None = None
    api_key: str | None = None  # raw API key — encrypted server-side
    from_address: str | None = None
    to_address: str | None = None
    notify_on_buy: bool | None = None
    notify_on_sell: bool | None = None


class EmailConfigResponse(BaseModel):
    enabled: bool = False
    api_key: str = ""  # masked as "••••••" when set
    from_address: str = ""
    to_address: str = ""
    notify_on_buy: bool = True
    notify_on_sell: bool = True


# ---- Exchange ----

class ExchangeAddRequest(BaseModel):
    name: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)
    passphrase: str | None = None
    quote_currencies: list[str] | None = None
    max_portfolio_pct: float | None = Field(None, gt=0, le=1)
    risk_overrides: dict[str, float] | None = None


class ExchangeUpdateRequest(BaseModel):
    """Update exchange credentials and settings — only provided fields are updated."""

    api_key: str | None = None
    api_secret: str | None = None
    passphrase: str | None = None
    quote_currencies: list[str] | None = None
    max_portfolio_pct: float | None = Field(None, gt=0, le=1)
    risk_overrides: dict[str, float] | None = None


class ExchangeResponse(BaseModel):
    id: str
    name: str
    exchange_type: str
    is_active: bool
    created_at: str
    quote_currencies: list[str] = ["USDT"]
    max_portfolio_pct: float = 1.0
    risk_overrides: dict[str, float] = {}


class ExchangeTestResponse(BaseModel):
    success: bool
    message: str


class AvailableExchangeResponse(BaseModel):
    name: str
    exchange_type: str
    default_fee_pct: float
    supports_websocket: bool
