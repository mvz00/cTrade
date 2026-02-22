"""FastAPI dependency injection providers."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ctrade.core.events import EventBus
from ctrade.db.engine import get_session
from ctrade.db.repositories.audit import AuditRepository
from ctrade.db.repositories.candles import CandleRepository
from ctrade.db.repositories.portfolio import PortfolioRepository
from ctrade.db.repositories.signals import SignalRepository
from ctrade.db.repositories.trades import OrderRepository, PositionRepository
from ctrade.settings import AppSettings, get_settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


def get_app_settings() -> AppSettings:
    """Provide application settings."""
    return get_settings()


def get_event_bus(request: Request) -> EventBus:
    """Provide the EventBus — prefers app.state, falls back to singleton."""
    bus: EventBus | None = getattr(request.app.state, "event_bus", None)
    if bus is not None:
        return bus
    return EventBus.get_instance()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: AppSettings = Depends(get_app_settings),
) -> str:
    """Validate JWT and return the username.

    When ``settings.auth.enabled`` is False, returns ``"anonymous"``
    so local dev works without tokens.
    """
    if not settings.auth.enabled:
        return "anonymous"

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from ctrade.core.exceptions import AuthenticationError
    from ctrade.security.auth import verify_access_token

    try:
        subject = verify_access_token(
            credentials.credentials,
            secret_key=settings.auth.secret_key.get_secret_value(),
            algorithm=settings.auth.algorithm,
        )
        return subject
    except AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


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
