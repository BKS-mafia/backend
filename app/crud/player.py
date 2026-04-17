"""
CRUD операции для модели Player.
"""
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas
from app.models.player import Player as PlayerModel


class PlayerCRUD:
    """
    Класс для операций CRUD с игроками.
    """

    async def create(self, db: AsyncSession, *, obj_in: schemas.PlayerCreate) -> PlayerModel:
        """
        Создать нового игрока.
        Заглушка: возвращает фиктивного игрока.
        """
        # TODO: реализовать создание игрока в БД
        from app.models.player import Player
        from datetime import datetime
        import uuid
        player = Player(
            id=1,
            player_id=str(uuid.uuid4()),
            room_id=obj_in.room_id,
            nickname=obj_in.nickname,
            is_ai=obj_in.is_ai,
            role=obj_in.role,
            is_alive=True,
            session_token=str(uuid.uuid4()),
            created_at=datetime.utcnow(),
            updated_at=None,
        )
        db.add(player)
        await db.commit()
        await db.refresh(player)
        return player

    async def get(self, db: AsyncSession, id: int) -> Optional[PlayerModel]:
        """
        Получить игрока по ID.
        Заглушка: возвращает None.
        """
        # TODO: реализовать запрос к БД
        return None

    async def get_by_session_token(
        self,
        db: AsyncSession,
        *,
        session_token: str,
    ) -> Optional[PlayerModel]:
        """
        Получить игрока по session_token.
        Заглушка: возвращает None.
        """
        # TODO: реализовать запрос к БД
        return None

    async def get_by_room(
        self,
        db: AsyncSession,
        *,
        room_id: int,
    ) -> List[PlayerModel]:
        """
        Получить всех игроков в комнате.
        Заглушка: возвращает пустой список.
        """
        # TODO: реализовать запрос к БД
        return []

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: PlayerModel,
        obj_in: schemas.PlayerUpdate,
    ) -> PlayerModel:
        """
        Обновить игрока.
        Заглушка: возвращает тот же объект.
        """
        # TODO: реализовать обновление
        return db_obj

    async def delete(self, db: AsyncSession, *, id: int) -> PlayerModel:
        """
        Удалить игрока.
        Заглушка: возвращает фиктивный объект.
        """
        # TODO: реализовать удаление
        from app.models.player import Player
        return Player()