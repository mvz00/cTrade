"""Base repository with common CRUD operations."""

from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ctrade.db.models import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Base repository providing common database operations."""

    def __init__(self, session: AsyncSession, model_class: type[ModelT]) -> None:
        self._session = session
        self._model_class = model_class

    async def get_by_id(self, entity_id: uuid.UUID | int) -> ModelT | None:
        """Fetch a single entity by its primary key."""
        return await self._session.get(self._model_class, entity_id)

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """Fetch all entities with pagination."""
        stmt = select(self._model_class).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, entity: ModelT) -> ModelT:
        """Add a new entity to the database."""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def create_many(self, entities: list[ModelT]) -> list[ModelT]:
        """Add multiple entities to the database."""
        self._session.add_all(entities)
        await self._session.flush()
        return entities

    async def update(self, entity: ModelT, **kwargs: Any) -> ModelT:
        """Update an entity's attributes."""
        for key, value in kwargs.items():
            setattr(entity, key, value)
        await self._session.flush()
        return entity

    async def delete(self, entity: ModelT) -> None:
        """Delete an entity from the database."""
        await self._session.delete(entity)
        await self._session.flush()

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self._session.commit()
