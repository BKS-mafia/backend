"""
CRUD операции для модели Game.
"""
from typing import Optional, List
import json
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app import schemas
from app.models.game import Game as GameModel, GameStatus
import logging

logger = logging.getLogger(__name__)


class GameCRUD:
    """
    Класс для операций CRUD с играми.
    """

    async def create(self, db: AsyncSession, *, obj_in: schemas.GameCreate) -> GameModel:
        """
        Создать новую запись игры.
        """
        # Преобразование статуса в enum
        try:
            status_enum = GameStatus(obj_in.status) if obj_in.status else GameStatus.LOBBY
        except ValueError:
            status_enum = GameStatus.LOBBY

        game = GameModel(
            room_id=obj_in.room_id,
            status=status_enum,
            day_number=obj_in.day_number if obj_in.day_number is not None else 1,
            night_actions=json.dumps(obj_in.night_actions) if obj_in.night_actions else None,
            voting_results=json.dumps(obj_in.voting_results) if obj_in.voting_results else None,
            winner=obj_in.winner,
        )
        db.add(game)
        await db.commit()
        await db.refresh(game)
        return game

    async def get(self, db: AsyncSession, id: int) -> Optional[GameModel]:
        """
        Получить игру по ID.
        """
        stmt = select(GameModel).where(GameModel.id == id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_room(
        self,
        db: AsyncSession,
        *,
        room_id: int,
    ) -> Optional[GameModel]:
        """
        Получить последнюю игру в комнате.
        """
        stmt = (
            select(GameModel)
            .where(GameModel.room_id == room_id)
            .order_by(desc(GameModel.id))
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_room(
        self,
        db: AsyncSession,
        *,
        room_id: int,
    ) -> List[GameModel]:
        """
        Получить все игры в комнате.
        """
        stmt = select(GameModel).where(GameModel.room_id == room_id).order_by(GameModel.id)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: GameModel,
        obj_in: schemas.GameUpdate,
    ) -> GameModel:
        """
        Обновить игру.
        """
        update_data = obj_in.dict(exclude_unset=True)
        if not update_data:
            return db_obj

        # Преобразование статуса в enum, если передан
        if "status" in update_data and update_data["status"] is not None:
            try:
                update_data["status"] = GameStatus(update_data["status"])
            except ValueError:
                del update_data["status"]

        # Сериализация JSON-полей
        if "night_actions" in update_data:
            update_data["night_actions"] = (
                json.dumps(update_data["night_actions"])
                if update_data["night_actions"] is not None
                else None
            )
        if "voting_results" in update_data:
            update_data["voting_results"] = (
                json.dumps(update_data["voting_results"])
                if update_data["voting_results"] is not None
                else None
            )

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def delete(self, db: AsyncSession, *, id: int) -> Optional[GameModel]:
        """
        Удалить игру.
        Возвращает удалённый объект или None, если не найден.
        """
        game = await self.get(db, id=id)
        if not game:
            return None

        await db.delete(game)
        await db.commit()
        return game

    async def save_turing_results(
        self,
        db: AsyncSession,
        game_id: int,
        turing_votes: dict,
        humanness_scores: dict,
    ) -> Optional[GameModel]:
        """
        Сохранить результаты теста Тьюринга:
        turing_votes   — словарь голосов {"player_id": [voter_id_1, voter_id_2], ...}
        humanness_scores — словарь скоров "человечности" {"player_id": 0.75, ...}
        """
        game = await self.get(db, id=game_id)
        if not game:
            logger.warning(f"save_turing_results: игра {game_id} не найдена")
            return None

        game.turing_votes = turing_votes
        game.humanness_scores = humanness_scores

        await db.commit()
        await db.refresh(game)
        return game
