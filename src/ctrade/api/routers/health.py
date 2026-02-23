"""Health check endpoint with database status.

The /health endpoint is used by Railway (and Docker HEALTHCHECK) to determine
whether the container is alive.  It MUST respond quickly and NEVER block on
external services (database, Redis, etc.).  We report cached DB status instead
of pinging the database on every health-check request.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint — always returns 200 immediately.

    Uses the cached DB availability flag from the main lifespan instead of
    calling ping_db() which can hang if the database is unreachable.
    """
    try:
        from ctrade.main import is_db_available
        db_ok = is_db_available()
    except Exception:
        db_ok = False

    return {
        "status": "ok",
        "service": "cTrade",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "connected" if db_ok else "unavailable",
    }
