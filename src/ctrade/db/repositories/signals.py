"""Repository for signal data operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ctrade.db.models import SignalModel
from ctrade.db.repositories.base import BaseRepository


class SignalRepository(BaseRepository[SignalModel]):
    """Repository for signal CRUD and queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SignalModel)

    async def get_recent_signals(
        self,
        pair_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[SignalModel]:
        """Get most recent signals, optionally filtered by pair."""
        stmt = select(SignalModel)
        if pair_id:
            stmt = stmt.where(SignalModel.pair_id == pair_id)
        stmt = stmt.order_by(SignalModel.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_signals_in_period(
        self,
        start: datetime,
        end: datetime,
        pair_id: uuid.UUID | None = None,
        action: str | None = None,
    ) -> list[SignalModel]:
        """Get signals within a time period."""
        conditions = [
            SignalModel.created_at >= start,
            SignalModel.created_at <= end,
        ]
        if pair_id:
            conditions.append(SignalModel.pair_id == pair_id)
        if action:
            conditions.append(SignalModel.action == action)

        stmt = (
            select(SignalModel)
            .where(and_(*conditions))
            .order_by(SignalModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
