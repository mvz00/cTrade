"""Signals API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from ctrade.api.schemas.signals import IndicatorResponse, SignalResponse
from ctrade.strategy.signal_manager import SignalManager

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/", response_model=list[SignalResponse])
async def list_signals(
    symbol: str | None = Query(None),
    action: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[SignalResponse]:
    """List recent trading signals."""
    mgr = SignalManager.get_instance()
    signals = mgr.list_signals(symbol=symbol, action=action, limit=limit)
    return [SignalResponse(**s) for s in signals]


@router.get("/{symbol:path}/latest", response_model=SignalResponse | None)
async def latest_signal(symbol: str) -> SignalResponse | None:
    """Get the latest signal for a symbol."""
    mgr = SignalManager.get_instance()
    s = mgr.get_latest(symbol)
    if s is None:
        return None
    return SignalResponse(**s)


@router.get("/{symbol:path}/indicators", response_model=IndicatorResponse | None)
async def get_indicators(symbol: str) -> IndicatorResponse | None:
    """Get current technical indicator values for a symbol."""
    mgr = SignalManager.get_instance()
    indicators = mgr.get_indicators(symbol)
    if indicators is None:
        return None
    return IndicatorResponse(
        symbol=symbol,
        indicators=indicators,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
