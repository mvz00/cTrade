"""Write-through cache persistence helper.

Provides async methods for singletons to load state from the database and
write-through on mutations.  All public functions are **fire-and-forget safe**
-- they log errors but never raise, so the caller's hot-path is never broken.

Usage pattern inside a singleton::

    from ctrade.db.persistence import fire_and_forget, is_db_ready, run_db_operation

    # synchronous mutation method (holds threading.Lock)
    def place_order(self, ...) -> Order:
        order = ...
        # ... update in-memory state ...
        fire_and_forget(self._persist_order(order))
        return order

    # async persist method
    async def _persist_order(self, order: Order) -> None:
        async def _do(session, resolver):
            from ctrade.db.mappers import order_to_orm
            orm = await order_to_orm(order, resolver)
            await session.merge(orm)
        await run_db_operation(_do, description="persist order")
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, TypeVar

from ctrade.db import engine as _engine_module  # submodule import, not re-export

logger = logging.getLogger(__name__)
T = TypeVar("T")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_db_ready() -> bool:
    """Return True if the database session factory has been initialised."""
    return _engine_module._session_factory is not None


async def get_fresh_session():  # -> AsyncSession | None
    """Create a new ``AsyncSession``, or return ``None`` if DB is unavailable."""
    factory = _engine_module._session_factory
    if factory is None:
        return None
    try:
        return factory()
    except Exception:
        logger.warning("Failed to create DB session", exc_info=True)
        return None


async def run_db_operation(
    operation: Callable[..., Coroutine[Any, Any, T]],
    *,
    description: str = "db operation",
) -> T | None:
    """Run *operation(session, resolver)* with full lifecycle management.

    * Opens a fresh session
    * Builds a ``PairResolver`` with pre-loaded caches
    * Commits on success, rolls back on error
    * Closes the session in all cases
    * **Never raises** -- returns ``None`` on failure
    """
    session = await get_fresh_session()
    if session is None:
        return None
    try:
        from ctrade.db.mappers import PairResolver

        resolver = PairResolver(session)
        await resolver.load_cache()
        result = await operation(session, resolver)
        await session.commit()
        return result
    except OSError as e:
        # Connection refused / network error — don't dump full traceback
        logger.warning("DB operation skipped (connection error): %s — %s", description, e)
        try:
            await session.rollback()
        except Exception:
            pass
        return None
    except Exception:
        logger.exception("DB operation failed: %s", description)
        try:
            await session.rollback()
        except Exception:
            pass
        return None
    finally:
        try:
            await session.close()
        except Exception:
            pass


async def run_simple_db_operation(
    operation: Callable[..., Coroutine[Any, Any, T]],
    *,
    description: str = "db operation",
) -> T | None:
    """Like ``run_db_operation`` but without ``PairResolver`` overhead.

    Calls ``operation(session)`` — useful for simple key-value operations
    (e.g. runtime_config upserts) that don't need pair/exchange ID resolution.
    """
    session = await get_fresh_session()
    if session is None:
        return None
    try:
        result = await operation(session)
        await session.commit()
        return result
    except OSError as e:
        logger.warning("Simple DB op skipped (connection error): %s — %s", description, e)
        try:
            await session.rollback()
        except Exception:
            pass
        return None
    except Exception:
        logger.exception("Simple DB op failed: %s", description)
        try:
            await session.rollback()
        except Exception:
            pass
        return None
    finally:
        try:
            await session.close()
        except Exception:
            pass


def fire_and_forget(coro: Coroutine[Any, Any, Any]) -> None:
    """Schedule *coro* on the running event loop without blocking the caller.

    Used by synchronous singleton methods (which hold a ``threading.Lock``)
    to trigger async DB writes after releasing the lock.

    * If no event loop is running (unit tests), the coroutine is silently
      discarded and a debug message is logged.
    * Any exception inside the coroutine is logged but never propagated.
    """
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(coro)
        task.add_done_callback(_log_task_exception)
    except RuntimeError:
        # No running event loop -- skip DB write (common in sync tests)
        logger.debug("No event loop available for fire-and-forget DB write")
        # Close the coroutine to avoid ResourceWarning
        coro.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _log_task_exception(task: asyncio.Task[Any]) -> None:
    """Callback attached to fire-and-forget tasks to log uncaught errors."""
    if not task.cancelled() and task.exception():
        logger.error(
            "Fire-and-forget DB task failed: %s",
            task.exception(),
            exc_info=task.exception(),
        )
