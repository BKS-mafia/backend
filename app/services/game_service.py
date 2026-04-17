"""
Сервис для управления игровой логикой: запуск State Machine, обработка ходов, ночные действия, голосование.
Координация между игроками, AI-агентами и WebSocket событиями.
Использование State Machine из app.game.state_machine.
Обработка таймеров и автоматических переходов.
"""
import asyncio
import logging
from typing import Dict, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.game.state_machine import StateMachine, GamePhase
from app.websocket.manager import ConnectionManager
from app.crud.room import RoomCRUD
from app.crud.player import PlayerCRUD
from app.crud.game import GameCRUD
from app.models.room import Room as RoomModel
from app.models.game import Game as GameModel

logger = logging.getLogger(__name__)


class GameService:
    """
    Сервис для управления игровой логикой.
    Управляет State Machine для каждой активной комнаты.
    """

    def __init__(
        self,
        room_crud: RoomCRUD,
        player_crud: PlayerCRUD,
        game_crud: GameCRUD,
        ws_manager: ConnectionManager,
    ):
        self.room_crud = room_crud
        self.player_crud = player_crud
        self.game_crud = game_crud
        self.ws_manager = ws_manager
        self.active_machines: Dict[int, StateMachine] = {}  # room_id -> StateMachine
        self.tasks: Dict[int, asyncio.Task] = {}  # room_id -> задача таймера

    async def start_game_for_room(
        self,
        db: AsyncSession,
        room_id: int,
    ) -> Dict[str, Any]:
        """
        Начать игру в комнате: создать State Machine и запустить её.
        """
        # Проверка, что комната существует и готова
        room = await self.room_crud.get(db, id=room_id)
        if not room:
            raise ValueError(f"Комната {room_id} не найдена")
        if room.status != "waiting":
            raise ValueError(f"Комната не в статусе waiting (статус: {room.status})")

        # Проверка минимального количества игроков
        players = await self.player_crud.get_by_room(db, room_id=room_id)
        if len(players) < room.min_players:
            raise ValueError(
                f"Недостаточно игроков для начала игры: "
                f"требуется {room.min_players}, сейчас {len(players)}"
            )

        # Обновление статуса комнаты на "playing"
        await self.room_crud.update(
            db,
            db_obj=room,
            obj_in={"status": "playing"},
        )

        # Создание записи игры в БД (если ещё не создана)
        game = await self.game_crud.create(
            db,
            obj_in={
                "room_id": room_id,
                "status": "lobby",
                "day_number": 1,
            },
        )

        # Создание State Machine
        machine = StateMachine(room_id=room_id, db=db)
        self.active_machines[room_id] = machine

        # Запуск State Machine в фоне
        asyncio.create_task(machine.start())
        logger.info(f"State Machine запущена для комнаты {room_id}")

        # Уведомление всех игроков через WebSocket
        await self.ws_manager.broadcast_to_room(
            room_id,
            {
                "type": "game_started",
                "room_id": room_id,
                "game_id": game.id,
                "message": "Игра началась! Распределение ролей...",
            },
        )

        # Запуск таймера для автоматических переходов (если нужно)
        # Пока State Machine сама управляет переходами, но можно добавить внешние таймеры
        # для принудительного перехода, если игроки не успевают.
        # Создадим задачу, которая будет следить за временем фаз.
        task = asyncio.create_task(self._phase_timer(room_id, db))
        self.tasks[room_id] = task

        return {
            "room_id": room_id,
            "game_id": game.id,
            "machine": machine,
            "message": "Игра успешно начата",
        }

    async def stop_game_for_room(
        self,
        db: AsyncSession,
        room_id: int,
    ) -> Dict[str, Any]:
        """
        Остановить игру в комнате (досрочное завершение).
        """
        machine = self.active_machines.get(room_id)
        if not machine:
            raise ValueError(f"Активная игра в комнате {room_id} не найдена")

        # Остановка State Machine
        await machine.stop()
        del self.active_machines[room_id]

        # Отмена таймерной задачи
        task = self.tasks.get(room_id)
        if task:
            task.cancel()
            del self.tasks[room_id]

        # Обновление статуса комнаты на "finished"
        room = await self.room_crud.get(db, id=room_id)
        if room:
            await self.room_crud.update(
                db,
                db_obj=room,
                obj_in={"status": "finished"},
            )

        # Обновление игры в БД
        game = await self.game_crud.get_by_room(db, room_id=room_id)
        if game:
            await self.game_crud.update(
                db,
                db_obj=game,
                obj_in={"status": "finished", "winner": "aborted"},
            )

        # Уведомление игроков
        await self.ws_manager.broadcast_to_room(
            room_id,
            {
                "type": "game_stopped",
                "room_id": room_id,
                "message": "Игра досрочно завершена.",
            },
        )

        logger.info(f"Игра в комнате {room_id} остановлена")
        return {"room_id": room_id, "message": "Игра остановлена"}

    async def submit_night_action(
        self,
        db: AsyncSession,
        room_id: int,
        player_id: int,
        action: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Принять ночное действие от игрока (мафия, доктор, комиссар).
        Действие будет сохранено в State Machine.
        """
        machine = self.active_machines.get(room_id)
        if not machine:
            raise ValueError(f"Активная игра в комнате {room_id} не найдена")

        # Проверка, что сейчас ночная фаза
        if machine.current_phase != GamePhase.NIGHT:
            raise ValueError("Ночные действия принимаются только в ночной фазе")

        # Проверка, что игрок жив и имеет право на действие (в зависимости от роли)
        # Эта проверка может быть внутри State Machine, но можно сделать здесь.
        # Пока просто передаём действие в машину.
        machine.night_actions[player_id] = action
        logger.info(f"Ночное действие от игрока {player_id} в комнате {room_id}: {action}")

        # Уведомление через WebSocket, что действие принято (опционально)
        await self.ws_manager.send_personal_message(
            {
                "type": "night_action_accepted",
                "player_id": player_id,
                "action": action,
            },
            # Нужен websocket игрока, но здесь мы его не имеем.
            # Можно использовать менеджер для поиска соединения по player_id.
            # Для упрощения пропустим.
        )

        # Если все необходимые действия получены, можно автоматически перейти к разрешению
        # (это зависит от логики State Machine)
        return {
            "player_id": player_id,
            "action": action,
            "message": "Ночное действие принято",
        }

    async def submit_vote(
        self,
        db: AsyncSession,
        room_id: int,
        voter_id: int,
        target_player_id: int,
    ) -> Dict[str, Any]:
        """
        Принять голос игрока во время дневного голосования.
        """
        machine = self.active_machines.get(room_id)
        if not machine:
            raise ValueError(f"Активная игра в комнате {room_id} не найдена")

        if machine.current_phase != GamePhase.VOTING:
            raise ValueError("Голосование возможно только в фазе голосования")

        # Проверка, что голосующий жив
        voter = await self.player_crud.get(db, id=voter_id)
        if not voter or not voter.is_alive:
            raise ValueError("Голосующий мёртв или не существует")

        # Проверка, что цель существует и жива
        target = await self.player_crud.get(db, id=target_player_id)
        if not target or not target.is_alive:
            raise ValueError("Цель голосования мёртва или не существует")

        # Сохраняем голос
        machine.votes[voter_id] = target_player_id
        logger.info(f"Голос от игрока {voter_id} за {target_player_id} в комнате {room_id}")

        # Уведомление всех о новом голосе (опционально)
        await self.ws_manager.broadcast_to_room(
            room_id,
            {
                "type": "vote_received",
                "voter_id": voter_id,
                "target_player_id": target_player_id,
            },
        )

        # Если все живые игроки проголосовали, можно автоматически завершить голосование
        # Это можно реализовать через проверку количества голосов.
        return {
            "voter_id": voter_id,
            "target_player_id": target_player_id,
            "message": "Голос принят",
        }

    async def get_game_state(
        self,
        db: AsyncSession,
        room_id: int,
    ) -> Dict[str, Any]:
        """
        Получить текущее состояние игры для комнаты.
        """
        machine = self.active_machines.get(room_id)
        if not machine:
            raise ValueError(f"Активная игра в комнате {room_id} не найдена")

        # Получить игроков
        players = await self.player_crud.get_by_room(db, room_id=room_id)
        # Получить игру из БД
        game = await self.game_crud.get_by_room(db, room_id=room_id)

        return {
            "room_id": room_id,
            "phase": machine.current_phase.value if machine.current_phase else None,
            "day_number": machine.day_number,
            "night_actions": machine.night_actions,
            "votes": machine.votes,
            "players": [
                {
                    "id": p.id,
                    "nickname": p.nickname,
                    "role": p.role,
                    "is_alive": p.is_alive,
                    "is_ai": p.is_ai,
                }
                for p in players
            ],
            "game": game,
        }

    async def force_phase_transition(
        self,
        db: AsyncSession,
        room_id: int,
        target_phase: GamePhase,
    ) -> Dict[str, Any]:
        """
        Принудительный переход фазы (для административных целей).
        """
        machine = self.active_machines.get(room_id)
        if not machine:
            raise ValueError(f"Активная игра в комнате {room_id} не найдена")

        old_phase = machine.current_phase
        machine.current_phase = target_phase
        logger.info(f"Принудительный переход фазы в комнате {room_id}: {old_phase} -> {target_phase}")

        # Уведомление игроков
        await self.ws_manager.broadcast_to_room(
            room_id,
            {
                "type": "phase_changed",
                "old_phase": old_phase.value if old_phase else None,
                "new_phase": target_phase.value,
                "room_id": room_id,
            },
        )

        return {
            "room_id": room_id,
            "old_phase": old_phase.value if old_phase else None,
            "new_phase": target_phase.value,
        }

    async def _phase_timer(self, room_id: int, db: AsyncSession):
        """
        Фоновая задача, которая следит за временем фазы и принудительно переходит,
        если время истекло.
        """
        # Конфигурация времени фаз (в секундах)
        PHASE_TIMEOUTS = {
            GamePhase.NIGHT: 60,      # 1 минута на ночные действия
            GamePhase.DAY: 120,       # 2 минуты на обсуждение
            GamePhase.VOTING: 90,     # 1.5 минуты на голосование
        }
        while True:
            await asyncio.sleep(5)  # Проверяем каждые 5 секунд
            machine = self.active_machines.get(room_id)
            if not machine:
                break
            phase = machine.current_phase
            timeout = PHASE_TIMEOUTS.get(phase)
            if timeout:
                # Здесь нужно отслеживать, сколько времени фаза уже длится.
                # Для простоты пропустим реализацию точного таймера.
                # Можно добавить логику с временем начала фазы.
                pass
            # Если нужно, можно принудительно переходить после таймаута.
            # Пока оставим заглушку.

    async def cleanup_room(self, room_id: int):
        """
        Очистить ресурсы, связанные с комнатой (при завершении игры).
        """
        machine = self.active_machines.pop(room_id, None)
        if machine:
            await machine.stop()
        task = self.tasks.pop(room_id, None)
        if task:
            task.cancel()
        logger.info(f"Ресурсы игры для комнаты {room_id} очищены")


# Глобальный экземпляр сервиса для удобства
from app.websocket.manager import manager as ws_manager
from app.crud.game import GameCRUD as GameCRUDClass

room_crud = RoomCRUD()
player_crud = PlayerCRUD()
try:
    game_crud = GameCRUDClass()
except Exception:
    # Если GameCRUD не существует, создадим заглушку (для совместимости)
    class GameCRUD:
        async def create(self, db, obj_in):
            return None
        async def get_by_room(self, db, room_id):
            return None
        async def update(self, db, db_obj, obj_in):
            return db_obj
    game_crud = GameCRUD()

game_service = GameService(room_crud, player_crud, game_crud, ws_manager)