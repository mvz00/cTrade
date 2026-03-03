"""Log history and diagnostic endpoints.

Serves historical log entries from the database when available, falling back
to the in-memory ring buffer in the ``LogPersister`` otherwise.  This means
the Logging page always has *some* history, even when there is no DB.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/logging", tags=["logging"])

_test_logger = logging.getLogger("ctrade.logging_test")


# ---- Schemas ----

class LogEntryResponse(BaseModel):
    id: int
    timestamp: str
    level: str
    logger: str
    message: str
    module: str
    func: str
    lineno: int


class LogHistoryResponse(BaseModel):
    entries: list[LogEntryResponse]
    total: int
    has_more: bool


# ---- Helpers ----

def _serve_from_memory(
    levels: list[str] | None,
    search: str | None,
    limit: int,
    offset: int,
) -> LogHistoryResponse:
    """Serve log history from the in-memory ring buffer."""
    from ctrade.db.log_persister import LogPersister

    try:
        persister = LogPersister.get_instance()
    except Exception:
        return LogHistoryResponse(entries=[], total=0, has_more=False)

    page, total = persister.get_recent_entries(
        levels=levels, search=search, limit=limit + 1, offset=offset,
    )

    has_more = len(page) > limit
    if has_more:
        page = page[:limit]

    entries = [
        LogEntryResponse(
            id=item.get("_mem_id", 0),
            timestamp=item.get("timestamp", ""),
            level=item.get("level", "INFO"),
            logger=item.get("logger", ""),
            message=item.get("message", ""),
            module=item.get("module", ""),
            func=item.get("func", ""),
            lineno=item.get("lineno", 0),
        )
        for item in page
    ]

    return LogHistoryResponse(entries=entries, total=total, has_more=has_more)


# ---- Endpoints ----

@router.get("/history", response_model=LogHistoryResponse)
async def log_history(
    level: str | None = Query(None, description="Comma-separated levels: DEBUG,INFO,WARNING,ERROR,CRITICAL"),
    search: str | None = Query(None, description="Search text (matches message, logger, module)"),
    start: datetime | None = Query(None, description="Start of time range (ISO 8601)"),
    end: datetime | None = Query(None, description="End of time range (ISO 8601)"),
    limit: int = Query(200, ge=1, le=2000, description="Max entries to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> LogHistoryResponse:
    """Fetch historical log entries.

    Uses the database when available; falls back to the in-memory ring buffer.
    Returns entries ordered by timestamp descending (newest first).
    """
    from ctrade.main import is_db_available

    levels: list[str] | None = None
    if level:
        levels = [lv.strip().upper() for lv in level.split(",") if lv.strip()]

    # --- Fallback: in-memory buffer ---
    if not is_db_available():
        return _serve_from_memory(levels, search, limit, offset)

    # --- Primary: database query ---
    from ctrade.db.persistence import run_simple_db_operation

    async def _query(session):  # type: ignore[no-untyped-def]
        from sqlalchemy import func, or_, select

        from ctrade.db.models import LogEntryModel

        stmt = select(LogEntryModel)

        if levels:
            stmt = stmt.where(LogEntryModel.level.in_(levels))
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    LogEntryModel.message.ilike(pattern),
                    LogEntryModel.logger.ilike(pattern),
                    LogEntryModel.module.ilike(pattern),
                )
            )
        if start:
            stmt = stmt.where(LogEntryModel.timestamp >= start)
        if end:
            stmt = stmt.where(LogEntryModel.timestamp <= end)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Fetch page (+1 to detect has_more)
        stmt = stmt.order_by(LogEntryModel.timestamp.desc())
        stmt = stmt.offset(offset).limit(limit + 1)
        result = await session.execute(stmt)
        rows = list(result.scalars().all())

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        entries = [
            LogEntryResponse(
                id=row.id,
                timestamp=row.timestamp.isoformat(),
                level=row.level,
                logger=row.logger,
                message=row.message,
                module=row.module,
                func=row.func,
                lineno=row.lineno,
            )
            for row in rows
        ]

        return LogHistoryResponse(entries=entries, total=total, has_more=has_more)

    result = await run_simple_db_operation(_query, description="fetch log history")
    if result:
        return result

    # DB operation failed — fall back to memory
    return _serve_from_memory(levels, search, limit, offset)


@router.post("/test")
async def logging_test() -> dict[str, str]:
    """Emit a test log entry to verify the logging pipeline."""
    _test_logger.info("Test log entry from /api/v1/logging/test")
    _test_logger.warning("Test WARNING from /api/v1/logging/test")
    return {"status": "ok", "message": "Test log entries emitted"}
