"""Batched log entry persistence — subscribes to EventBus LOG_ENTRY events."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

from ctrade.db.persistence import is_db_ready, run_simple_db_operation

logger = logging.getLogger(__name__)

_FLUSH_INTERVAL_SECONDS = 2.0
_FLUSH_BATCH_SIZE = 50
_CLEANUP_INTERVAL_SECONDS = 3600  # 1 hour
_RETENTION_DAYS = 7


class LogPersister:
    """Buffers LOG_ENTRY events and flushes them to the database in batches.

    Singleton — use ``get_instance()`` to access.

    - Subscribes to ``EventTypes.LOG_ENTRY`` on the EventBus.
    - Buffers entries in memory.
    - Flushes every 2 seconds OR when buffer hits 50 entries.
    - Runs retention cleanup hourly (deletes entries older than 7 days).
    - Gracefully degrades if DB is unavailable (drops entries silently).
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
        self._buffer: list[dict[str, Any]] = []
        self._buffer_lock = threading.Lock()
        self._running = False
        self._flush_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background flush and cleanup loops."""
        if self._running:
            return
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
        await self._flush_buffer()

    async def handle_log_event(self, event: Any) -> None:
        """EventBus handler — called for each LOG_ENTRY event."""
        data = event.data
        with self._buffer_lock:
            self._buffer.append(data)
            buffer_len = len(self._buffer)

        if buffer_len >= _FLUSH_BATCH_SIZE:
            await self._flush_buffer()

    async def _flush_loop(self) -> None:
        """Periodic flush every _FLUSH_INTERVAL_SECONDS."""
        while self._running:
            try:
                await asyncio.sleep(_FLUSH_INTERVAL_SECONDS)
                await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in log flush loop")

    async def _flush_buffer(self) -> None:
        """Flush buffered entries to the database."""
        with self._buffer_lock:
            if not self._buffer:
                return
            batch = self._buffer[:]
            self._buffer.clear()

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

    async def _cleanup_loop(self) -> None:
        """Periodically delete log entries older than _RETENTION_DAYS."""
        while self._running:
            try:
                await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)
                await self._run_cleanup()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in log cleanup loop")

    async def _run_cleanup(self) -> None:
        """Delete log entries older than retention period."""
        if not is_db_ready():
            return

        cutoff = datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)

        async def _do(session: Any) -> None:
            from sqlalchemy import delete

            from ctrade.db.models import LogEntryModel

            result = await session.execute(
                delete(LogEntryModel).where(LogEntryModel.created_at < cutoff)
            )
            count = result.rowcount
            if count and count > 0:
                logger.info(
                    "Log retention cleanup: deleted %d entries older than %d days",
                    count, _RETENTION_DAYS,
                )

        await run_simple_db_operation(_do, description="log retention cleanup")
