"""
CRUD операции для модели Room.
"""
from typing import Optional, List
import json
import uuid
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas
from app.models.room import Room as RoomModel, RoomStatus


class RoomCRUD:
    """
    Класс для операций CRUD с комнатами.
    """

    async def create(self, db: AsyncSession, *, obj_in: schemas.RoomCreate) -> RoomModel:
        """
        Создать новую комнату.
        """
        # Преобразуем статус в перечисление RoomStatus
        try:
            status_enum = RoomStatus(obj_in.status) if obj_in.status else RoomStatus.LOBBY
        except ValueError:
            status_enum = RoomStatus.LOBBY

        # Генерируем room_id, если не предоставлен
        room_id = obj_in.room_id.strip() if obj_in.room_id else None
        if not room_id:
            room_id = str(uuid.uuid4())

        # Генерируем host_token, если не предоставлен
        host_token = obj_in.host_token.strip() if obj_in.host_token else None
        if not host_token:
            host_token = str(uuid.uuid4())

        room = RoomModel(
            room_id=room_id,
            host_token=host_token,
            status=status_enum,
            max_players=obj_in.max_players,
            min_players=obj_in.min_players,
            current_players=obj_in.current_players,
            ai_players=obj_in.ai_players,
            human_players=obj_in.human_players,
            settings=json.dumps(obj_in.settings) if obj_in.settings else None,
        )
        db.add(room)
        await db.commit()
        await db.refresh(room)
        return room

    async def get(self, db: AsyncSession, id: int) -> Optional[RoomModel]:
        """
        Получить комнату по внутреннему ID.
        """
        stmt = select(RoomModel).where(RoomModel.id == id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_room_id(self, db: AsyncSession, *, room_id: str) -> Optional[RoomModel]:
        """
        Получить комнату по публичному room_id (UUID).
        """
        stmt = select(RoomModel).where(RoomModel.room_id == room_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_host_token(self, db: AsyncSession, *, host_token: str) -> Optional[RoomModel]:
        """
        Получить комнату по host_token.
        """
        stmt = select(RoomModel).where(RoomModel.host_token == host_token)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self, db: AsyncSession) -> List[RoomModel]:
        """
        Получить все комнаты.
        """
        stmt = select(RoomModel)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_active(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> List[RoomModel]:
        """
        Получить активные комнаты (статус LOBBY или STARTING) с пагинацией.
        Используется для браузера комнат.
        """
        stmt = (
            select(RoomModel)
            .where(
                or_(
                    RoomModel.status == RoomStatus.LOBBY,
                    RoomModel.status == RoomStatus.STARTING,
                )
            )
            .order_by(RoomModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: RoomModel,
        obj_in: schemas.RoomUpdate,
    ) -> RoomModel:
        """
        Обновить комнату.
        """
        update_data = obj_in.dict(exclude_unset=True)
        if not update_data:
            return db_obj

        # Преобразование статуса в enum, если передан
        if "status" in update_data and update_data["status"] is not None:
            try:
                update_data["status"] = RoomStatus(update_data["status"])
            except ValueError:
                del update_data["status"]

        # Сериализация settings в JSON
        if "settings" in update_data:
            update_data["settings"] = (
                json.dumps(update_data["settings"])
                if update_data["settings"] is not None
                else None
            )

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def delete(self, db: AsyncSession, *, id: int) -> Optional[RoomModel]:
        """
        Удалить комнату.
        Возвращает удалённый объект или None, если не найден.
        """
        room = await self.get(db, id=id)
        if not room:
            return None

        await db.delete(room)
        await db.commit()
        return room
