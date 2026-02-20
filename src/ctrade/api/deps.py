"""FastAPI dependency injection providers."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ctrade.db.engine import get_session
from ctrade.db.repositories.audit import AuditRepository
from ctrade.db.repositories.candles import CandleRepository
from ctrade.db.repositories.portfolio import PortfolioRepository
from ctrade.db.repositories.signals import SignalRepository
from ctrade.db.repositories.trades import OrderRepository, PositionRepository
from ctrade.settings import AppSettings, get_settings


def get_app_settings() -> AppSettings:
    """Provide application settings."""
    return get_settings()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session."""
    async for session in get_session():
        yield session


async def get_order_repo(
    session: AsyncSession = Depends(get_db_session),
) -> OrderRepository:
    """Provide an order repository."""
    return OrderRepository(session)


async def get_position_repo(
    session: AsyncSession = Depends(get_db_session),
) -> PositionRepository:
    """Provide a position repository."""
    return PositionRepository(session)


async def get_candle_repo(
    session: AsyncSession = Depends(get_db_session),
) -> CandleRepository:
    """Provide a candle repository."""
    return CandleRepository(session)


async def get_signal_repo(
    session: AsyncSession = Depends(get_db_session),
) -> SignalRepository:
    """Provide a signal repository."""
    return SignalRepository(session)


async def get_portfolio_repo(
    session: AsyncSession = Depends(get_db_session),
) -> PortfolioRepository:
    """Provide a portfolio repository."""
    return PortfolioRepository(session)


async def get_audit_repo(
    session: AsyncSession = Depends(get_db_session),
) -> AuditRepository:
    """Provide an audit repository."""
    return AuditRepository(session)
