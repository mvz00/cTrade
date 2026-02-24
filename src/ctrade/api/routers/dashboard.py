"""Dashboard API endpoints — real data from active engine and system status."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query

from ctrade.core.config_store import RuntimeConfigStore
from ctrade.exchange.engine_resolver import get_engine
from ctrade.exchange.paper_engine import PaperEngine
from ctrade.strategy.orchestrator import TradingOrchestrator

logger = logging.getLogger(__name__)

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
        from ctrade.feeds.cvd import CVDFeed
        from ctrade.feeds.derivatives import DerivativesFeed
        from ctrade.feeds.market_sentiment import MarketSentimentFeed
        from ctrade.feeds.onchain import OnChainFeed
        from ctrade.feeds.sentiment import SentimentFeed
        from ctrade.feeds.social_velocity import SocialVelocityFeed

        db_ok = await ping_db()
        sentiment = SentimentFeed.get_instance()
        onchain = OnChainFeed.get_instance()
        derivatives = DerivativesFeed.get_instance()
        mkt_sentiment = MarketSentimentFeed.get_instance()
        cvd = CVDFeed.get_instance()
        social_velocity = SocialVelocityFeed.get_instance()

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
            "cvd_feed": {
                "status": "ok" if cvd.is_enabled and await cvd.healthcheck() else "warning",
                "label": (
                    f"Active ({cvd.get_status()['symbols_tracked']} symbols)"
                    if cvd.is_enabled
                    else "Inactive"
                ),
            },
            "social_velocity_feed": {
                "status": "ok" if social_velocity.is_enabled and await social_velocity.healthcheck() else "warning",
                "label": (
                    f"Active ({social_velocity.get_status()['assets_tracked']} assets)"
                    if social_velocity.is_enabled
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


# ---------- Range string → timedelta mapping ----------
_RANGE_DELTAS: dict[str, timedelta | None] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "all": None,  # unbounded — use a very early start
}


@router.get("/portfolio-history")
async def get_portfolio_history(
    range: str = Query("7d", pattern="^(24h|7d|30d|90d|all)$"),
) -> list[dict[str, Any]]:
    """Return portfolio snapshots grouped by exchange for charting.

    Each item in the list represents one exchange's time series::

        [
          {
            "exchange_id": "uuid-string",
            "exchange_name": "coinspot",
            "points": [
              {"timestamp": "2024-01-01T00:00:00+00:00", "total_value_usd": 2750.0},
              ...
            ]
          },
          ...
        ]
    """
    from ctrade.db.engine import _session_factory
    from ctrade.db.repositories.portfolio import PortfolioRepository

    if _session_factory is None:
        return []

    try:
        store = RuntimeConfigStore.get()
        trading_mode = store.get_trading().get("mode", "paper")
    except RuntimeError:
        return []

    now = datetime.now(timezone.utc)
    delta = _RANGE_DELTAS.get(range)
    start = now - delta if delta else datetime(2020, 1, 1, tzinfo=timezone.utc)

    async with _session_factory() as session:
        repo = PortfolioRepository(session)
        snapshots = await repo.get_all_snapshots_in_period(
            trading_mode=trading_mode,
            start=start,
            end=now,
        )

    if not snapshots:
        return []

    # Build a name lookup from RuntimeConfigStore
    exchange_names: dict[str, str] = {}
    try:
        for ex in store.list_exchanges():
            raw_id = ex.get("id")
            ex_uuid = str(raw_id) if raw_id else ""
            exchange_names[ex_uuid] = ex.get("name", "unknown")
    except Exception:
        pass

    # Group snapshots by exchange_id
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snap in snapshots:
        eid = str(snap.exchange_id)
        grouped[eid].append({
            "timestamp": snap.time.isoformat(),
            "total_value_usd": float(snap.total_value_usd),
        })

    return [
        {
            "exchange_id": eid,
            "exchange_name": exchange_names.get(eid, "unknown"),
            "points": points,
        }
        for eid, points in grouped.items()
    ]
