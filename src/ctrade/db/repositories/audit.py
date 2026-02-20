"""Repository for audit log operations."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ctrade.db.models import AuditLogModel


class AuditRepository:
    """Repository for writing and querying the audit log."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        event_type: str,
        details: dict[str, Any],
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> AuditLogModel:
        """Write an audit log entry."""
        entry = AuditLogModel(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def get_recent(
        self,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditLogModel]:
        """Get recent audit log entries."""
        stmt = select(AuditLogModel)
        if event_type:
            stmt = stmt.where(AuditLogModel.event_type == event_type)
        stmt = stmt.order_by(AuditLogModel.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
