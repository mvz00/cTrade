"""Repository for order and position operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ctrade.db.models import OrderModel, PositionModel
from ctrade.db.repositories.base import BaseRepository


class OrderRepository(BaseRepository[OrderModel]):
    """Repository for order CRUD and queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OrderModel)

    async def get_active_orders(self, exchange_id: uuid.UUID | None = None) -> list[OrderModel]:
        """Get all active (non-terminal) orders."""
        active_statuses = ("pending", "submitted", "partially_filled")
        stmt = select(OrderModel).where(OrderModel.status.in_(active_statuses))
        if exchange_id:
            stmt = stmt.where(OrderModel.exchange_id == exchange_id)
        stmt = stmt.order_by(OrderModel.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_orders_for_pair(
        self,
        pair_id: uuid.UUID,
        limit: int = 50,
    ) -> list[OrderModel]:
        """Get recent orders for a specific trading pair."""
        stmt = (
            select(OrderModel)
            .where(OrderModel.pair_id == pair_id)
            .order_by(OrderModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_orders_in_period(
        self,
        start: datetime,
        end: datetime,
        trading_mode: str | None = None,
    ) -> list[OrderModel]:
        """Get orders within a time period."""
        conditions = [
            OrderModel.created_at >= start,
            OrderModel.created_at <= end,
        ]
        if trading_mode:
            conditions.append(OrderModel.trading_mode == trading_mode)
        stmt = (
            select(OrderModel)
            .where(and_(*conditions))
            .order_by(OrderModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class PositionRepository(BaseRepository[PositionModel]):
    """Repository for position CRUD and queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PositionModel)

    async def get_open_positions(
        self,
        exchange_id: uuid.UUID | None = None,
        trading_mode: str | None = None,
    ) -> list[PositionModel]:
        """Get all open positions."""
        conditions = [PositionModel.status == "open"]
        if exchange_id:
            conditions.append(PositionModel.exchange_id == exchange_id)
        if trading_mode:
            conditions.append(PositionModel.trading_mode == trading_mode)
        stmt = (
            select(PositionModel)
            .where(and_(*conditions))
            .order_by(PositionModel.opened_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_closed_positions(
        self,
        limit: int = 50,
        trading_mode: str | None = None,
    ) -> list[PositionModel]:
        """Get recently closed positions."""
        conditions = [PositionModel.status == "closed"]
        if trading_mode:
            conditions.append(PositionModel.trading_mode == trading_mode)
        stmt = (
            select(PositionModel)
            .where(and_(*conditions))
            .order_by(PositionModel.closed_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_position_for_pair(
        self,
        pair_id: uuid.UUID,
        exchange_id: uuid.UUID,
        trading_mode: str,
    ) -> PositionModel | None:
        """Get the open position for a specific pair on an exchange, if any."""
        stmt = select(PositionModel).where(
            and_(
                PositionModel.pair_id == pair_id,
                PositionModel.exchange_id == exchange_id,
                PositionModel.trading_mode == trading_mode,
                PositionModel.status == "open",
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
