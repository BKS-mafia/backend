"""
CRUD операции для модели Room.
"""
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas
from app.models.room import Room as RoomModel


class RoomCRUD:
    """
    Класс для операций CRUD с комнатами.
    """

    async def create(self, db: AsyncSession, *, obj_in: schemas.RoomCreate) -> RoomModel:
        """
        Создать новую комнату.
        Заглушка: возвращает фиктивную комнату.
        """
        # TODO: реализовать создание комнаты в БД
        from app.models.room import Room
        from datetime import datetime
        import uuid
        room = Room(
            id=1,
            room_id=str(uuid.uuid4()),
            host_token=obj_in.host_token,
            status=obj_in.status,
            max_players=obj_in.max_players,
            min_players=obj_in.min_players,
            current_players=obj_in.current_players,
            ai_players=obj_in.ai_players,
            human_players=obj_in.human_players,
            settings=obj_in.settings,
            created_at=datetime.utcnow(),
            updated_at=None,
        )
        db.add(room)
        await db.commit()
        await db.refresh(room)
        return room

    async def get(self, db: AsyncSession, id: int) -> Optional[RoomModel]:
        """
        Получить комнату по ID.
        Заглушка: возвращает None.
        """
        # TODO: реализовать запрос к БД
        return None

    async def get_by_room_id(self, db: AsyncSession, *, room_id: str) -> Optional[RoomModel]:
        """
        Получить комнату по публичному room_id (UUID).
        Заглушка: возвращает None.
        """
        # TODO: реализовать запрос к БД
        return None

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: RoomModel,
        obj_in: schemas.RoomUpdate,
    ) -> RoomModel:
        """
        Обновить комнату.
        Заглушка: возвращает тот же объект.
        """
        # TODO: реализовать обновление
        return db_obj

    async def delete(self, db: AsyncSession, *, id: int) -> RoomModel:
        """
        Удалить комнату.
        Заглушка: возвращает фиктивный объект.
        """
        # TODO: реализовать удаление
        from app.models.room import Room
        return Room()