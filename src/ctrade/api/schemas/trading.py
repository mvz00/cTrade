"""Pydantic schemas for trading endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AddPairRequest(BaseModel):
    symbol: str = Field(min_length=3, examples=["BTC/USDT"])


class AddPairsBatchRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)


class PairResponse(BaseModel):
    symbol: str
    is_active: bool = True


class PlaceOrderRequest(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"] = "market"
    quantity: float = Field(gt=0)
    price: float | None = None


class OrderResponse(BaseModel):
    id: str
    signal_id: str | None = None
    pair_symbol: str
    trading_mode: str
    order_type: str
    side: str
    quantity: float
    price: float | None = None
    status: str
    filled_quantity: float
    avg_fill_price: float | None = None
    fee: float
    fee_currency: str
    error_message: str | None = None
    created_at: str
    filled_at: str | None = None


class PositionResponse(BaseModel):
    id: str
    pair_symbol: str
    side: str
    status: str
    entry_price: float
    exit_price: float | None = None
    quantity: float
    stop_loss: float | None = None
    take_profit: float | None = None
    realized_pnl: float | None = None
    realized_pnl_pct: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pnl_pct: float | None = None
    current_price: float | None = None
    fees_total: float
    strategy_name: str
    opened_at: str
    closed_at: str | None = None
    justification: str = ""


class PortfolioResponse(BaseModel):
    cash_balance: dict[str, float]
    total_value_usd: float
    positions_value: float
    unrealized_pnl: float
    realized_pnl: float
    daily_pnl: float
    open_positions: int
    closed_positions: int
    total_orders: int


class EngineStatusResponse(BaseModel):
    running: bool
    tick_count: int
    last_tick: str | None = None
    interval_seconds: int


class EngineStartRequest(BaseModel):
    interval: int | None = Field(None, ge=5, le=3600)


class TickerResponse(BaseModel):
    symbol: str
    last_price: float
    bid: float
    ask: float
    high_24h: float
    low_24h: float
    volume_24h: float
    change_pct_24h: float


class ActivityEntry(BaseModel):
    time: str
    type: str
    pair: str
    message: str
    details: dict[str, Any] = {}
