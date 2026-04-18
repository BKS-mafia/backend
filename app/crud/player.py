"""
CRUD операции для модели Player.
"""
from typing import Optional, List
import uuid
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas
from app.models.player import Player as PlayerModel, PlayerRole


class PlayerCRUD:
    """
    Класс для операций CRUD с игроками.
    """

    async def create(self, db: AsyncSession, *, obj_in: schemas.PlayerCreate) -> PlayerModel:
        """
        Создать нового игрока.
        """
        # Генерация player_id, если не предоставлен или пустой
        player_id = obj_in.player_id.strip() if obj_in.player_id else None
        if not player_id:
            player_id = str(uuid.uuid4())

        # Генерация session_token, если не предоставлен
        session_token = obj_in.session_token
        if session_token is None:
            session_token = str(uuid.uuid4())

        # Преобразование роли в enum, если указана
        role_enum = None
        if obj_in.role:
            try:
                role_enum = PlayerRole(obj_in.role)
            except ValueError:
                # Если роль некорректна, оставляем None
                pass

        player = PlayerModel(
            player_id=player_id,
            room_id=obj_in.room_id,
            nickname=obj_in.nickname,
            is_ai=obj_in.is_ai,
            role=role_enum,
            is_alive=obj_in.is_alive,
            is_connected=obj_in.is_connected,
            session_token=session_token,
        )
        db.add(player)
        await db.commit()
        await db.refresh(player)
        return player

    async def get(self, db: AsyncSession, id: int) -> Optional[PlayerModel]:
        """
        Получить игрока по ID.
        """
        stmt = select(PlayerModel).where(PlayerModel.id == id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_session_token(
        self,
        db: AsyncSession,
        *,
        session_token: str,
    ) -> Optional[PlayerModel]:
        """
        Получить игрока по session_token.
        """
        stmt = select(PlayerModel).where(PlayerModel.session_token == session_token)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_room(
        self,
        db: AsyncSession,
        *,
        room_id: int,
    ) -> List[PlayerModel]:
        """
        Получить всех игроков в комнате.
        """
        stmt = select(PlayerModel).where(PlayerModel.room_id == room_id)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: PlayerModel,
        obj_in: schemas.PlayerUpdate,
    ) -> PlayerModel:
        """
        Обновить игрока.
        """
        update_data = obj_in.dict(exclude_unset=True)
        if not update_data:
            return db_obj

        # Преобразование роли в enum, если передана
        if "role" in update_data and update_data["role"] is not None:
            try:
                update_data["role"] = PlayerRole(update_data["role"])
            except ValueError:
                # Если роль некорректна, удаляем поле из обновления
                del update_data["role"]

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def delete(self, db: AsyncSession, *, id: int) -> Optional[PlayerModel]:
        """
        Удалить игрока.
        Возвращает удалённый объект или None, если не найден.
        """
        player = await self.get(db, id=id)
        if not player:
            return None

        await db.delete(player)
        await db.commit()
        return player