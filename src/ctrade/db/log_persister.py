"""Batched log entry persistence and data retention cleanup.

Always keeps an in-memory ring buffer of recent log entries so the Logging
page can show history even when the database is unavailable.  When the DB *is*
reachable, entries are also flushed there in batches for cross-restart
persistence.

Also runs periodic retention cleanup for ALL accumulating tables:
- **Log tables** (log_entries, audit_log) — governed by ``log_rollover_days``
- **Data tables** (signals, orders, positions, candles, sentiment_data,
  onchain_metrics, portfolio_snapshots, alert_history) — governed by
  ``data_rollover_days``
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

from ctrade.db.persistence import is_db_ready, run_simple_db_operation

logger = logging.getLogger(__name__)

_FLUSH_INTERVAL_SECONDS = 2.0
_FLUSH_BATCH_SIZE = 50
_CLEANUP_INTERVAL_SECONDS = 3600  # 1 hour
_DEFAULT_LOG_RETENTION_DAYS = 7
_DEFAULT_DATA_RETENTION_DAYS = 30
_MEMORY_BUFFER_SIZE = 2000  # Max entries kept in memory


class LogPersister:
    """Buffers LOG_ENTRY events and optionally flushes them to the database.

    Singleton — use ``get_instance()`` to access.

    - Always keeps the last *_MEMORY_BUFFER_SIZE* entries in a ring buffer.
    - When the DB is available, also batch-flushes to ``log_entries`` table.
    - Runs retention cleanup hourly for ALL accumulating tables.
    - Gracefully degrades if DB is unavailable (in-memory only).
    """

    _instance: ClassVar[LogPersister | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def get_instance(cls) -> LogPersister:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        # In-memory ring buffer — always active
        self._ring: deque[dict[str, Any]] = deque(maxlen=_MEMORY_BUFFER_SIZE)
        self._ring_lock = threading.Lock()
        self._next_mem_id = 1  # Incrementing ID for in-memory entries

        # DB flush buffer
        self._db_buffer: list[dict[str, Any]] = []
        self._db_buffer_lock = threading.Lock()

        # Configurable retention (loaded from RuntimeConfigStore on start)
        self.log_retention_days: int = _DEFAULT_LOG_RETENTION_DAYS
        self.data_retention_days: int = _DEFAULT_DATA_RETENTION_DAYS

        self._running = False
        self._flush_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None

    # ---- In-memory query ----

    def get_recent_entries(
        self,
        *,
        levels: list[str] | None = None,
        search: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return entries from the in-memory ring buffer.

        Returns (entries_page, total_matching) with entries in newest-first order.
        """
        with self._ring_lock:
            all_entries = list(self._ring)

        # Filter
        if levels:
            upper_levels = {lv.upper() for lv in levels}
            all_entries = [e for e in all_entries if e.get("level", "").upper() in upper_levels]
        if search:
            search_lower = search.lower()
            all_entries = [
                e for e in all_entries
                if search_lower in e.get("message", "").lower()
                or search_lower in e.get("logger", "").lower()
                or search_lower in e.get("module", "").lower()
            ]

        total = len(all_entries)

        # Newest first
        all_entries.reverse()

        # Paginate
        page = all_entries[offset : offset + limit]
        return page, total

    def clear_all_buffers(self) -> int:
        """Clear both the in-memory ring buffer and the pending DB flush buffer.

        Returns the number of ring-buffer entries cleared.  Must be called
        during purge so the next flush cycle doesn't re-populate the DB.
        """
        with self._ring_lock:
            count = len(self._ring)
            self._ring.clear()
            self._next_mem_id = 1
        with self._db_buffer_lock:
            self._db_buffer.clear()
        return count

    def set_retention_days(self, *, log_days: int | None = None, data_days: int | None = None) -> None:
        """Update retention periods (hot-reload from config)."""
        if log_days is not None:
            self.log_retention_days = max(1, min(log_days, 365))
        if data_days is not None:
            self.data_retention_days = max(1, min(data_days, 365))

    # ---- Lifecycle ----

    async def start(self) -> None:
        """Start the background flush and cleanup loops."""
        if self._running:
            return

        # Load retention days from config store if available
        try:
            from ctrade.core.config_store import RuntimeConfigStore
            if RuntimeConfigStore.is_initialized():
                cfg = RuntimeConfigStore.get().get_logging_config()
                self.log_retention_days = cfg.get("log_rollover_days", _DEFAULT_LOG_RETENTION_DAYS)
                self.data_retention_days = cfg.get("data_rollover_days", _DEFAULT_DATA_RETENTION_DAYS)
        except Exception:
            pass  # Use defaults

        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """Stop loops and flush remaining buffer."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        # Final flush
        await self._flush_db_buffer()

    # ---- Event handling ----

    async def handle_log_event(self, event: Any) -> None:
        """EventBus handler — called for each LOG_ENTRY event."""
        data = event.data

        # Always add to in-memory ring buffer
        with self._ring_lock:
            mem_id = self._next_mem_id
            self._next_mem_id += 1
            data_with_id = {**data, "_mem_id": mem_id}
            self._ring.append(data_with_id)

        # Also buffer for DB flush if DB is available
        if is_db_ready():
            with self._db_buffer_lock:
                self._db_buffer.append(data)
                buffer_len = len(self._db_buffer)

            if buffer_len >= _FLUSH_BATCH_SIZE:
                await self._flush_db_buffer()

    # ---- DB flush ----

    async def _flush_loop(self) -> None:
        """Periodic flush every _FLUSH_INTERVAL_SECONDS."""
        while self._running:
            try:
                await asyncio.sleep(_FLUSH_INTERVAL_SECONDS)
                await self._flush_db_buffer()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in log flush loop")

    async def _flush_db_buffer(self) -> None:
        """Flush buffered entries to the database."""
        with self._db_buffer_lock:
            if not self._db_buffer:
                return
            batch = self._db_buffer[:]
            self._db_buffer.clear()

        if not is_db_ready():
            return

        async def _do(session: Any) -> None:
            from ctrade.db.models import LogEntryModel

            objects = []
            for entry in batch:
                try:
                    ts = datetime.fromisoformat(entry["timestamp"])
                except (KeyError, ValueError, TypeError):
                    ts = datetime.now(timezone.utc)

                objects.append(LogEntryModel(
                    timestamp=ts,
                    level=entry.get("level", "INFO"),
                    logger=entry.get("logger", ""),
                    message=entry.get("message", ""),
                    module=entry.get("module", ""),
                    func=entry.get("func", ""),
                    lineno=entry.get("lineno", 0),
                ))
            session.add_all(objects)

        await run_simple_db_operation(_do, description=f"flush {len(batch)} log entries")

    # ---- Retention cleanup ----

    async def _cleanup_loop(self) -> None:
        """Periodically run retention cleanup for all accumulating tables."""
        while self._running:
            try:
                await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)
                await self._run_cleanup()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in retention cleanup loop")

    async def _run_cleanup(self) -> None:
        """Delete old entries from all accumulating tables."""
        if not is_db_ready():
            return

        log_cutoff = datetime.now(timezone.utc) - timedelta(days=self.log_retention_days)
        data_cutoff = datetime.now(timezone.utc) - timedelta(days=self.data_retention_days)

        async def _do(session: Any) -> None:
            from sqlalchemy import delete

            from ctrade.db.models import (
                AlertHistoryModel,
                AuditLogModel,
                CandleModel,
                LogEntryModel,
                OnChainMetricModel,
                OrderModel,
                PortfolioSnapshotModel,
                PositionModel,
                SentimentDataModel,
                SignalModel,
            )

            total = 0

            # --- Log tables (log_rollover_days) ---
            r = await session.execute(
                delete(LogEntryModel).where(LogEntryModel.created_at < log_cutoff)
            )
            if r.rowcount:
                total += r.rowcount

            r = await session.execute(
                delete(AuditLogModel).where(AuditLogModel.created_at < log_cutoff)
            )
            if r.rowcount:
                total += r.rowcount

            # --- Data tables (data_rollover_days) ---
            r = await session.execute(
                delete(SignalModel).where(SignalModel.created_at < data_cutoff)
            )
            if r.rowcount:
                total += r.rowcount

            r = await session.execute(
                delete(OrderModel).where(OrderModel.created_at < data_cutoff)
            )
            if r.rowcount:
                total += r.rowcount

            # Only clean closed positions older than cutoff
            r = await session.execute(
                delete(PositionModel).where(
                    PositionModel.opened_at < data_cutoff,
                    PositionModel.status == "closed",
                )
            )
            if r.rowcount:
                total += r.rowcount

            r = await session.execute(
                delete(CandleModel).where(CandleModel.time < data_cutoff)
            )
            if r.rowcount:
                total += r.rowcount

            r = await session.execute(
                delete(SentimentDataModel).where(SentimentDataModel.time < data_cutoff)
            )
            if r.rowcount:
                total += r.rowcount

            r = await session.execute(
                delete(OnChainMetricModel).where(OnChainMetricModel.time < data_cutoff)
            )
            if r.rowcount:
                total += r.rowcount

            r = await session.execute(
                delete(PortfolioSnapshotModel).where(PortfolioSnapshotModel.time < data_cutoff)
            )
            if r.rowcount:
                total += r.rowcount

            r = await session.execute(
                delete(AlertHistoryModel).where(AlertHistoryModel.created_at < data_cutoff)
            )
            if r.rowcount:
                total += r.rowcount

            if total > 0:
                logger.info(
                    "Retention cleanup: deleted %d total rows (logs>%dd, data>%dd)",
                    total, self.log_retention_days, self.data_retention_days,
                )

        await run_simple_db_operation(_do, description="retention cleanup (all tables)")
