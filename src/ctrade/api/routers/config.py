"""Configuration API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ctrade.api.deps import get_app_settings
from ctrade.settings import AppSettings

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/trading-mode")
async def get_trading_mode(
    settings: AppSettings = Depends(get_app_settings),
) -> dict[str, str]:
    """Get current trading mode (paper/live)."""
    return {"mode": settings.trading.mode}


@router.get("/strategy")
async def get_strategy_config(
    settings: AppSettings = Depends(get_app_settings),
) -> dict:
    """Get current strategy configuration."""
    return {
        "active_strategy": settings.strategy.active_strategy,
        "technical_weight": settings.strategy.technical_weight,
        "sentiment_weight": settings.strategy.sentiment_weight,
        "onchain_weight": settings.strategy.onchain_weight,
        "entry_confidence_threshold": settings.strategy.entry_confidence_threshold,
        "exit_confidence_threshold": settings.strategy.exit_confidence_threshold,
    }


@router.get("/risk")
async def get_risk_config(
    settings: AppSettings = Depends(get_app_settings),
) -> dict:
    """Get current risk management configuration."""
    return {
        "max_position_pct": settings.risk.max_position_pct,
        "max_daily_loss_pct": settings.risk.max_daily_loss_pct,
        "max_drawdown_pct": settings.risk.max_drawdown_pct,
        "default_stop_loss_pct": settings.risk.default_stop_loss_pct,
        "default_take_profit_pct": settings.risk.default_take_profit_pct,
    }
