"""Repository for portfolio snapshot operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ctrade.db.models import PortfolioSnapshotModel
from ctrade.db.repositories.base import BaseRepository


class PortfolioRepository(BaseRepository[PortfolioSnapshotModel]):
    """Repository for portfolio snapshot CRUD and queries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PortfolioSnapshotModel)

    async def get_latest_snapshot(
        self,
        exchange_id: uuid.UUID,
        trading_mode: str,
    ) -> PortfolioSnapshotModel | None:
        """Get the most recent portfolio snapshot."""
        stmt = (
            select(PortfolioSnapshotModel)
            .where(
                and_(
                    PortfolioSnapshotModel.exchange_id == exchange_id,
                    PortfolioSnapshotModel.trading_mode == trading_mode,
                )
            )
            .order_by(PortfolioSnapshotModel.time.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_snapshots_in_period(
        self,
        exchange_id: uuid.UUID,
        trading_mode: str,
        start: datetime,
        end: datetime,
    ) -> list[PortfolioSnapshotModel]:
        """Get portfolio snapshots within a time period (for equity curve)."""
        stmt = (
            select(PortfolioSnapshotModel)
            .where(
                and_(
                    PortfolioSnapshotModel.exchange_id == exchange_id,
                    PortfolioSnapshotModel.trading_mode == trading_mode,
                    PortfolioSnapshotModel.time >= start,
                    PortfolioSnapshotModel.time <= end,
                )
            )
            .order_by(PortfolioSnapshotModel.time.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
