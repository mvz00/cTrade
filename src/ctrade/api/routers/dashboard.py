"""Dashboard API endpoints — real data from active engine and system status."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ctrade.core.config_store import RuntimeConfigStore
from ctrade.exchange.engine_resolver import get_engine
from ctrade.exchange.paper_engine import PaperEngine
from ctrade.strategy.orchestrator import TradingOrchestrator

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def get_dashboard_summary() -> dict[str, Any]:
    """Get dashboard summary with portfolio value, P&L, and active feeds."""
    try:
        engine = get_engine()
        portfolio = await engine.get_portfolio()
        store = RuntimeConfigStore.get()
        trading = store.get_trading()

        return {
            "total_value_usd": portfolio["total_value_usd"],
            "daily_pnl": portfolio["daily_pnl"],
            "open_positions": portfolio["open_positions"],
            "active_feeds": len(PaperEngine.get_instance().get_watched_pairs()),
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
        engine = get_engine()
        return engine.get_equity_curve()
    except RuntimeError:
        return []


@router.get("/recent-trades")
async def get_recent_trades(
    limit: int = Query(20, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Get recent closed trades."""
    try:
        engine = get_engine()
        return engine.get_recent_trades(limit=limit)
    except RuntimeError:
        return []


@router.get("/status")
async def get_system_status() -> dict[str, Any]:
    """Get system component health status."""
    try:
        # Watched pairs are shared via PaperEngine
        paper = PaperEngine.get_instance()
        orch = TradingOrchestrator.get_instance()
        store = RuntimeConfigStore.get()
        exchanges = store.list_exchanges()

        from ctrade.db.engine import ping_db
        from ctrade.feeds.derivatives import DerivativesFeed
        from ctrade.feeds.market_sentiment import MarketSentimentFeed
        from ctrade.feeds.onchain import OnChainFeed
        from ctrade.feeds.sentiment import SentimentFeed

        db_ok = await ping_db()
        sentiment = SentimentFeed.get_instance()
        onchain = OnChainFeed.get_instance()
        derivatives = DerivativesFeed.get_instance()
        mkt_sentiment = MarketSentimentFeed.get_instance()

        return {
            "api_server": {"status": "ok", "label": "Online"},
            "database": {
                "status": "ok" if db_ok else "warning",
                "label": "Connected" if db_ok else "In-memory mode",
            },
            "exchange": {
                "status": "ok" if exchanges else "warning",
                "label": f"{len(exchanges)} configured" if exchanges else "Not configured",
            },
            "trading_engine": {
                "status": "ok" if orch.is_running else "warning",
                "label": "Running" if orch.is_running else "Stopped",
            },
            "sentiment_feed": {
                "status": "ok" if sentiment.is_enabled and await sentiment.healthcheck() else "warning",
                "label": "Active" if sentiment.is_enabled else "Inactive",
            },
            "onchain_feed": {
                "status": "ok" if onchain.is_enabled and await onchain.healthcheck() else "warning",
                "label": "Active" if onchain.is_enabled else "Inactive",
            },
            "derivatives_feed": {
                "status": "ok" if derivatives.is_enabled and await derivatives.healthcheck() else "warning",
                "label": (
                    f"Active ({derivatives.get_status()['symbols_tracked']} symbols)"
                    if derivatives.is_enabled
                    else "Inactive (no exchange)"
                ),
            },
            "market_sentiment_feed": {
                "status": "ok" if mkt_sentiment.is_enabled and await mkt_sentiment.healthcheck() else "warning",
                "label": (
                    f"Active (F&G: {mkt_sentiment.get_fear_greed()['value']}, "
                    f"{mkt_sentiment.get_status()['long_short_symbols']} L/S symbols)"
                    if mkt_sentiment.is_enabled
                    else "Inactive"
                ),
            },
            "event_bus": {"status": "ok", "label": "Running"},
            "watched_pairs": len(paper.get_watched_pairs()),
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
