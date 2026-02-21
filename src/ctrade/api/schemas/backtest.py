"""Pydantic schemas for backtesting endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    symbol: str = Field(min_length=3, examples=["BTC/USDT"])
    initial_capital: float = Field(default=10000.0, gt=0)
    num_candles: int = Field(default=200, ge=50, le=1000)
    timeframe: str = Field(default="1h")
    entry_threshold: float = Field(default=0.65, ge=0, le=1)
    exit_threshold: float = Field(default=0.35, ge=0, le=1)


class BacktestTradeResponse(BaseModel):
    pair_symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    entry_time: str
    exit_time: str


class BacktestResultResponse(BaseModel):
    id: str
    symbol: str
    initial_capital: float
    final_value: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown_pct: float
    sharpe_ratio: float
    equity_curve: list[dict[str, Any]]
    trade_log: list[BacktestTradeResponse]
    created_at: str
