"""Backtesting API endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ctrade.api.schemas.backtest import BacktestRequest, BacktestResultResponse
from ctrade.backtest.engine import BacktestEngine

router = APIRouter(prefix="/backtest", tags=["backtest"])

# Module-level engine instance (in-memory results)
_engine = BacktestEngine()


@router.post("/run", response_model=BacktestResultResponse)
async def run_backtest(body: BacktestRequest) -> BacktestResultResponse:
    """Run a backtest with the specified parameters."""
    result = await _engine.run(
        symbol=body.symbol,
        initial_capital=body.initial_capital,
        num_candles=body.num_candles,
        timeframe=body.timeframe,
        entry_threshold=body.entry_threshold,
        exit_threshold=body.exit_threshold,
    )
    return BacktestResultResponse(**result)


@router.get("/results", response_model=list[BacktestResultResponse])
async def list_results() -> list[BacktestResultResponse]:
    """List past backtest results."""
    return [BacktestResultResponse(**r) for r in _engine.get_results()]
