"""
Сервис для управления комнатами (создание, получение, присоединение игроков, старт игры).
Использует CRUD операции из app.crud.room и app.crud.player.
Интегрируется с WebSocket менеджером для уведомлений.
Валидирует бизнес-правила (максимальное количество игроков, статусы комнаты).
"""
import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.crud.room import RoomCRUD
from app.crud.player import PlayerCRUD
from app.websocket.manager import ConnectionManager
from app.models.room import Room as RoomModel
from app.models.player import Player as PlayerModel
from app.utils.short_id import generate_unique_short_id

logger = logging.getLogger(__name__)


class RoomService:
    """
    Сервис для управления комнатами.
    """

    def __init__(
        self,
        room_crud: RoomCRUD,
        player_crud: PlayerCRUD,
        ws_manager: ConnectionManager,
    ):
        self.room_crud = room_crud
        self.player_crud = player_crud
        self.ws_manager = ws_manager

    async def create_room(
        self,
        db: AsyncSession,
        room_create: schemas.RoomCreate,
    ) -> RoomModel:
        """
        Создать новую комнату с валидацией.
        """
        # Валидация количества игроков
        if room_create.total_players > 20:
            raise ValueError("Общее количество игроков не может превышать 20")
        if room_create.total_players < 3:
            raise ValueError("Общее количество игроков не может быть меньше 3")
        if room_create.ai_count + room_create.people_count != room_create.total_players:
            raise ValueError(
                "Сумма AI и людей должна быть равна общему количеству игроков"
            )

        # Проверка уникальности room_id (если требуется) - можно добавить проверку в CRUD
        # Пока создаём комнату
        room = await self.room_crud.create(db, obj_in=room_create)
        logger.info(f"Создана комната {room.id} с room_id={room.room_id}")
        # Уведомление через WebSocket не требуется, так как нет подключённых клиентов
        return room

    async def get_room(
        self,
        db: AsyncSession,
        room_id: int,
    ) -> Optional[RoomModel]:
        """
        Получить комнату по ID.
        """
        return await self.room_crud.get(db, id=room_id)

    async def get_room_by_public_id(
        self,
        db: AsyncSession,
        public_room_id: str,
    ) -> Optional[RoomModel]:
        """
        Получить комнату по публичному room_id (UUID).
        """
        return await self.room_crud.get_by_room_id(db, room_id=public_room_id)

    async def get_room_by_short_id(
        self,
        db: AsyncSession,
        short_id: str,
    ) -> Optional[RoomModel]:
        """
        Получить комнату по short_id.
        """
        return await self.room_crud.get_by_short_id(db, short_id=short_id)

    async def update_room(
        self,
        db: AsyncSession,
        room_id: int,
        room_update: schemas.RoomUpdate,
    ) -> RoomModel:
        """
        Обновить комнату с валидацией.
        """
        room = await self.room_crud.get(db, id=room_id)
        if not room:
            raise ValueError(f"Комната с ID {room_id} не найдена")

        # Валидация изменения количества игроков
        if room_update.total_players is not None:
            if room_update.total_players > 20:
                raise ValueError("Общее количество игроков не может превышать 20")
            if room_update.total_players < 3:
                raise ValueError("Общее количество игроков не может быть меньше 3")

        # Проверка, что current_players не превышает total_players
        if room_update.current_players is not None:
            total_players = room_update.total_players or room.total_players
            if room_update.current_players > total_players:
                raise ValueError(
                    f"Текущее количество игроков ({room_update.current_players}) "
                    f"превышает общее ({total_players})"
                )

        updated_room = await self.room_crud.update(
            db, db_obj=room, obj_in=room_update
        )
        logger.info(f"Комната {room_id} обновлена")

        # Если статус комнаты изменился, уведомить всех подключённых игроков
        if room_update.status is not None and room_update.status != room.status:
            await self.ws_manager.broadcast_to_room(
                room_id,
                {
                    "type": "room_status_changed",
                    "room_id": room_id,
                    "new_status": room_update.status,
                },
            )
        return updated_room

    async def delete_room(
        self,
        db: AsyncSession,
        room_id: int,
    ) -> RoomModel:
        """
        Удалить комнату и уведомить всех подключённых игроков.
        """
        room = await self.room_crud.delete(db, id=room_id)
        logger.info(f"Комната {room_id} удалена")

        # Уведомление о закрытии комнаты
        await self.ws_manager.broadcast_to_room(
            room_id,
            {
                "type": "room_deleted",
                "room_id": room_id,
            },
        )
        return room

    async def join_player(
        self,
        db: AsyncSession,
        room_id: int,
        player_create: schemas.PlayerCreate,
    ) -> PlayerModel:
        """
        Добавить игрока в комнату с проверкой доступности мест.
        """
        room = await self.room_crud.get(db, id=room_id)
        if not room:
            raise ValueError(f"Комната с ID {room_id} не найдена")

        # Проверка, что комната не в статусе "playing" или "finished"
        if room.status in ("playing", "finished"):
            raise ValueError("Нельзя присоединиться к игре, которая уже началась или завершена")

        # Проверка максимального количества игроков
        if room.current_players >= room.total_players:
            raise ValueError("Комната заполнена")

        # Проверка, что игрок с таким nickname уже не присутствует в комнате (опционально)
        # Для простоты пропускаем

        # Гарантируем, что room_id в схеме совпадает с внутренним ID комнаты (Pydantic v2)
        player_create = player_create.model_copy(update={"room_id": room_id})
        player = await self.player_crud.create(db, obj_in=player_create)
        logger.info(f"Игрок {player.id} присоединился к комнате {room_id}")

        # Обновляем счётчик игроков в комнате
        await self.room_crud.update(
            db,
            db_obj=room,
            obj_in=schemas.RoomUpdate(
                current_players=room.current_players + 1,
                human_players=room.human_players + (0 if player_create.is_ai else 1),
                ai_players=room.ai_players + (1 if player_create.is_ai else 0),
            ),
        )

        # Уведомляем всех в комнате о новом игроке
        await self.ws_manager.broadcast_to_room(
            room_id,
            {
                "type": "player_joined",
                "player_id": player.id,
                "nickname": player.nickname,
                "is_ai": player.is_ai,
                "current_players": room.current_players + 1,
            },
        )
        return player

    async def start_game(
        self,
        db: AsyncSession,
        room_id: int,
    ) -> Dict[str, Any]:
        """
        Начать игру в комнате (перевести статус в "playing").
        Запускает State Machine (это должен делать GameService).
        Пока только меняем статус комнаты.
        """
        room = await self.room_crud.get(db, id=room_id)
        if not room:
            raise ValueError(f"Комната с ID {room_id} не найдена")

        # Проверка количества игроков
        if room.current_players < room.total_players:
            raise ValueError(
                f"Недостаточно игроков для начала игры: "
                f"требуется {room.total_players}, сейчас {room.current_players}"
            )

        # Проверка, что комната в статусе "waiting"
        if room.status != "waiting":
            raise ValueError(f"Комната не готова к началу игры (статус: {room.status})")

        # Обновление статуса комнаты
        updated_room = await self.room_crud.update(
            db,
            db_obj=room,
            obj_in=schemas.RoomUpdate(status="playing"),
        )

        logger.info(f"Игра в комнате {room_id} начата")

        # Уведомление всех игроков
        await self.ws_manager.broadcast_to_room(
            room_id,
            {
                "type": "game_started",
                "room_id": room_id,
            },
        )

        # Возвращаем информацию о комнате и игроках
        players = await self.player_crud.get_by_room(db, room_id=room_id)
        return {
            "room": updated_room,
            "players": players,
            "message": "Игра начата",
        }


# Глобальный экземпляр сервиса для удобства (можно использовать dependency injection)
room_crud = RoomCRUD()
player_crud = PlayerCRUD()
from app.websocket.manager import manager as ws_manager
room_service = RoomService(room_crud, player_crud, ws_manager)
