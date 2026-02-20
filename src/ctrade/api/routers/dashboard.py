"""Dashboard API endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def get_dashboard_summary() -> dict:
    """Get dashboard summary with portfolio value, P&L, and active feeds."""
    # Placeholder — will be implemented in Phase 4
    return {
        "total_value_usd": 0,
        "daily_pnl": 0,
        "open_positions": 0,
        "active_feeds": 0,
        "trading_mode": "paper",
    }
