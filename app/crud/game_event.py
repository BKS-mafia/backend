"""
CRUD операции для модели GameEvent.
"""
from typing import Optional, List
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas
from app.models.game_event import GameEvent as GameEventModel


class GameEventCRUD:
    """
    Класс для операций CRUD с игровыми событиями.
    """

    async def create(
        self, db: AsyncSession, *, obj_in: schemas.GameEventCreate
    ) -> GameEventModel:
        """
        Создать новое игровое событие.
        """
        event = GameEventModel(
            game_id=obj_in.game_id,
            player_id=obj_in.player_id,
            event_type=obj_in.event_type,
            event_data=json.dumps(obj_in.event_data) if obj_in.event_data else None,
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event

    async def get(self, db: AsyncSession, id: int) -> Optional[GameEventModel]:
        """
        Получить событие по ID.
        """
        stmt = select(GameEventModel).where(GameEventModel.id == id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_game(
        self,
        db: AsyncSession,
        *,
        game_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> List[GameEventModel]:
        """
        Получить все события для игры с пагинацией.
        """
        stmt = (
            select(GameEventModel)
            .where(GameEventModel.game_id == game_id)
            .order_by(GameEventModel.id)
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_by_game_and_type(
        self,
        db: AsyncSession,
        *,
        game_id: int,
        event_type: str,
    ) -> List[GameEventModel]:
        """
        Получить события определённого типа для игры.
        """
        stmt = (
            select(GameEventModel)
            .where(
                GameEventModel.game_id == game_id,
                GameEventModel.event_type == event_type,
            )
            .order_by(GameEventModel.id)
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    async def delete(self, db: AsyncSession, *, id: int) -> Optional[GameEventModel]:
        """
        Удалить событие.
        """
        event = await self.get(db, id=id)
        if not event:
            return None
        await db.delete(event)
        await db.commit()
        return event
