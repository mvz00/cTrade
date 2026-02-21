"""SQLAlchemy async engine and session factory."""

from __future__ import annotations

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
    )
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info("Database engine initialized: pool_size=%d", pool_size)


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


async def ping_db() -> bool:
    """Ping the database to check connectivity.

    Returns ``True`` if a simple ``SELECT 1`` succeeds, ``False`` otherwise.
    Never raises.
    """
    if _engine is None:
        return False
    try:
        from sqlalchemy import text

        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def close_db() -> None:
    """Close the database engine and all connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine closed")
