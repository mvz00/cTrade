"""Repository for candle (OHLCV) data operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ctrade.db.models import CandleModel


class CandleRepository:
    """Repository for candle CRUD and queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_candles(self, candles: list[CandleModel]) -> int:
        """Insert candles, updating on conflict (same time + pair + timeframe).

        Returns the number of rows affected.
        """
        if not candles:
            return 0

        values = [
            {
                "time": c.time,
                "pair_id": c.pair_id,
                "timeframe": c.timeframe,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]

        stmt = insert(CandleModel).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["time", "pair_id", "timeframe"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
            },
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount  # type: ignore[return-value]

    async def get_candles(
        self,
        pair_id: uuid.UUID,
        timeframe: str,
        limit: int = 200,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[CandleModel]:
        """Get candles for a pair, ordered by time descending."""
        conditions = [
            CandleModel.pair_id == pair_id,
            CandleModel.timeframe == timeframe,
        ]
        if start:
            conditions.append(CandleModel.time >= start)
        if end:
            conditions.append(CandleModel.time <= end)

        stmt = (
            select(CandleModel)
            .where(and_(*conditions))
            .order_by(CandleModel.time.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_candle_time(
        self,
        pair_id: uuid.UUID,
        timeframe: str,
    ) -> datetime | None:
        """Get the timestamp of the most recent candle."""
        from sqlalchemy import func

        stmt = (
            select(func.max(CandleModel.time))
            .where(
                and_(
                    CandleModel.pair_id == pair_id,
                    CandleModel.timeframe == timeframe,
                )
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
