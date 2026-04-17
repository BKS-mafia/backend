"""
CRUD операции для модели Game.
"""
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas
from app.models.game import Game as GameModel


class GameCRUD:
    """
    Класс для операций CRUD с играми.
    """

    async def create(self, db: AsyncSession, *, obj_in: schemas.GameCreate) -> GameModel:
        """
        Создать новую запись игры.
        Заглушка: возвращает фиктивную игру.
        """
        # TODO: реализовать создание игры в БД
        from app.models.game import Game
        from datetime import datetime
        game = Game(
            id=1,
            room_id=obj_in.room_id,
            status=obj_in.status,
            day_number=obj_in.day_number,
            night_actions=None,
            voting_results=None,
            winner=None,
            created_at=datetime.utcnow(),
            updated_at=None,
        )
        db.add(game)
        await db.commit()
        await db.refresh(game)
        return game

    async def get(self, db: AsyncSession, id: int) -> Optional[GameModel]:
        """
        Получить игру по ID.
        Заглушка: возвращает None.
        """
        # TODO: реализовать запрос к БД
        return None

    async def get_by_room(
        self,
        db: AsyncSession,
        *,
        room_id: int,
    ) -> Optional[GameModel]:
        """
        Получить активную игру в комнате (последнюю).
        Заглушка: возвращает None.
        """
        # TODO: реализовать запрос к БД
        return None

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: GameModel,
        obj_in: schemas.GameUpdate,
    ) -> GameModel:
        """
        Обновить игру.
        Заглушка: возвращает тот же объект.
        """
        # TODO: реализовать обновление
        return db_obj

    async def delete(self, db: AsyncSession, *, id: int) -> GameModel:
        """
        Удалить игру.
        Заглушка: возвращает фиктивный объект.
        """
        # TODO: реализовать удаление
        from app.models.game import Game
        return Game()