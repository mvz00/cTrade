"""Dashboard API endpoints — real data from paper engine and system status."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ctrade.core.config_store import RuntimeConfigStore
from ctrade.exchange.paper_engine import PaperEngine
from ctrade.strategy.orchestrator import TradingOrchestrator

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def get_dashboard_summary() -> dict[str, Any]:
    """Get dashboard summary with portfolio value, P&L, and active feeds."""
    try:
        engine = PaperEngine.get_instance()
        portfolio = engine.get_portfolio()
        store = RuntimeConfigStore.get()
        trading = store.get_trading()

        return {
            "total_value_usd": portfolio["total_value_usd"],
            "daily_pnl": portfolio["daily_pnl"],
            "open_positions": portfolio["open_positions"],
            "active_feeds": len(engine.get_watched_pairs()),
            "trading_mode": trading.get("mode", "paper"),
        }
    except RuntimeError:
        return {
            "total_value_usd": 10000,
            "daily_pnl": 0,
            "open_positions": 0,
            "active_feeds": 0,
            "trading_mode": "paper",
        }


@router.get("/equity-curve")
async def get_equity_curve() -> list[dict[str, Any]]:
    """Get portfolio equity curve over time."""
    try:
        engine = PaperEngine.get_instance()
        return engine.get_equity_curve()
    except RuntimeError:
        return []


@router.get("/recent-trades")
async def get_recent_trades(
    limit: int = Query(20, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Get recent closed trades."""
    try:
        engine = PaperEngine.get_instance()
        return engine.get_recent_trades(limit=limit)
    except RuntimeError:
        return []


@router.get("/status")
async def get_system_status() -> dict[str, Any]:
    """Get system component health status."""
    try:
        engine = PaperEngine.get_instance()
        orch = TradingOrchestrator.get_instance()
        store = RuntimeConfigStore.get()
        exchanges = store.list_exchanges()

        return {
            "api_server": {"status": "ok", "label": "Online"},
            "database": {"status": "warning", "label": "In-memory mode"},
            "exchange": {
                "status": "ok" if exchanges else "warning",
                "label": f"{len(exchanges)} configured" if exchanges else "Not configured",
            },
            "trading_engine": {
                "status": "ok" if orch.is_running else "warning",
                "label": "Running" if orch.is_running else "Stopped",
            },
            "event_bus": {"status": "ok", "label": "Running"},
            "watched_pairs": len(engine.get_watched_pairs()),
        }
    except RuntimeError:
        return {
            "api_server": {"status": "ok", "label": "Online"},
            "database": {"status": "warning", "label": "Not connected"},
            "exchange": {"status": "warning", "label": "Not configured"},
            "trading_engine": {"status": "warning", "label": "Stopped"},
            "event_bus": {"status": "ok", "label": "Running"},
            "watched_pairs": 0,
        }
