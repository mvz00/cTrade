"""Health check endpoint with database status."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint with database connectivity status."""
    from ctrade.db.engine import ping_db

    db_ok = await ping_db()

    return {
        "status": "ok",
        "service": "cTrade",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "connected" if db_ok else "unavailable",
    }
