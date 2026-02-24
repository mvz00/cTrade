"""SQLAlchemy async engine and session factory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

# Module-level references, initialized by init_db()
_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

# Short timeout for asyncpg connections (default is 60s which blocks startup)
_CONNECT_TIMEOUT_SECONDS = 5


def init_db(database_url: str, pool_size: int = 10, echo: bool = False) -> None:
    """Initialize the database engine and session factory.

    Args:
        database_url: Async database URL (postgresql+asyncpg://...).
        pool_size: Connection pool size.
        echo: If True, log all SQL statements.
    """
    global _engine, _session_factory

    _engine = create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=pool_size,
        echo=echo,
        pool_pre_ping=True,
        connect_args={"timeout": _CONNECT_TIMEOUT_SECONDS},
    )
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info("Database engine initialized: pool_size=%d, connect_timeout=%ds", pool_size, _CONNECT_TIMEOUT_SECONDS)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session. Used as a FastAPI dependency."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def ping_db(timeout: float = 10.0) -> bool:
    """Ping the database to check connectivity.

    Returns ``True`` if a simple ``SELECT 1`` succeeds within *timeout*
    seconds, ``False`` otherwise.  Never raises.
    """
    if _engine is None:
        return False
    try:
        from sqlalchemy import text

        async def _ping() -> bool:
            async with _engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True

        return await asyncio.wait_for(_ping(), timeout=timeout)
    except (asyncio.TimeoutError, Exception) as exc:
        logger.debug("ping_db failed: %s", exc)
        return False


async def ensure_tables() -> None:
    """Create any missing tables defined in the ORM models.

    Uses ``CREATE TABLE IF NOT EXISTS`` semantics — safe to call on every
    startup.  Existing tables and data are never modified.
    """
    if _engine is None:
        logger.warning("ensure_tables called before init_db — skipping")
        return
    try:
        from ctrade.db.models import Base

        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified / created")
    except Exception:
        logger.exception("Failed to ensure tables — some tables may be missing")


_DISPOSE_TIMEOUT_SECONDS = 5


async def close_db() -> None:
    """Close the database engine and all connections.

    Uses a timeout to avoid hanging if asyncpg has pending connections
    (e.g. from a cancelled ping attempt against an unreachable host).
    """
    global _engine, _session_factory
    if _engine is not None:
        try:
            await asyncio.wait_for(_engine.dispose(), timeout=_DISPOSE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(
                "Engine dispose timed out after %ds — forcing cleanup",
                _DISPOSE_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning("Engine dispose failed: %s", exc)
        _engine = None
        _session_factory = None
        logger.info("Database engine closed")
