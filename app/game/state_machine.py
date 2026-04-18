import asyncio
import random
import time
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set
from app.models.room import Room, RoomStatus
from app.models.player import Player, PlayerRole
from app.models.game import Game, GameStatus
from app.models.game_event import GameEvent
from app.db.session import AsyncSession
from sqlalchemy import select, update
import json
import logging

if TYPE_CHECKING:
    from app.websocket.manager import ConnectionManager
    from app.services.ai_service import AIService
    from app.ai.mcp_tools import MCPToolDispatcher

logger = logging.getLogger(__name__)


class GamePhase(str, Enum):
    LOBBY = "lobby"
    ROLE_ASSIGNMENT = "role_assignment"
    NIGHT = "night"
    DAY = "day"
    VOTING = "voting"
    TURING_TEST = "turing_test"
    FINISHED = "finished"


class StateMachine:
    def __init__(
        self,
        room_id: int,
        db: AsyncSession,
        ws_manager: Optional["ConnectionManager"] = None,
        game_id: Optional[int] = None,
        players: Optional[list] = None,
        ai_service: Optional["AIService"] = None,
        mcp_dispatcher: Optional["MCPToolDispatcher"] = None,
    ) -> None:
        self.room_id = room_id
        self.db = db
        self.ws_manager = ws_manager
        self.game_id: Optional[int] = game_id
        self.players: list = players or []
        self.ai_service = ai_service
        self.mcp_dispatcher = mcp_dispatcher

        self.current_phase = GamePhase.LOBBY
        self.night_actions: Dict[int, Dict[str, Any]] = {}  # player_id -> action
        self.votes: Dict[int, int] = {}  # voter_id -> target_player_id
        self.day_number: int = 1
        self.night_number: int = 0
        self.is_running: bool = False
        self.task: Optional[asyncio.Task] = None
        # Итоги последней ночи для рассылки в начале дня
        self.night_summary: Dict[str, Any] = {}
        # История дневного чата для контекста ИИ
        self.day_chat_history: List[dict] = []
        # Ссылка на GameService для управления таймерами фаз (устанавливается извне)
        self.game_service = None
        # Победитель игры (устанавливается в check_game_over)
        self.winner: Optional[str] = None
        # Голоса в Тесте Тьюринга: {suspect_player_id: [voter_id_1, ...]}
        self.turing_votes: Dict[int, List[int]] = {}
        
        # Счётчик ошибок AI для каждого бота: {player_id: error_count}
        self.ai_error_counts: Dict[int, int] = {}
        # Последнее fallback-сообщение для каждого бота (чтобы не повторять)
        self.ai_last_fallback: Dict[int, str] = {}
        # Трекинг последнего отправленного сообщения для защиты от дублирования
        self.ai_last_message: Dict[int, str] = {}
        # Таймстемп последнего сообщения для защиты от дублирования
        self.ai_last_message_time: Dict[int, float] = {}

        self._register_dispatcher_callbacks()

    # ------------------------------------------------------------------
    # Регистрация колбэков MCP dispatcher
    # ------------------------------------------------------------------

    def _register_dispatcher_callbacks(self) -> None:
        """Регистрируем колбэки MCP dispatcher."""
        if not self.mcp_dispatcher:
            return
        self.mcp_dispatcher.register_send_message(self._process_ai_chat_message)
        self.mcp_dispatcher.register_vote(self._process_ai_vote)
        self.mcp_dispatcher.register_night_action(self._process_ai_night_action)
        self.mcp_dispatcher.register_get_game_state(self._get_game_state_for_ai)

    # ------------------------------------------------------------------
    # Запуск / остановка
    # ------------------------------------------------------------------

    async def start(self):
        """Start the state machine."""
        if self.is_running:
            return
        self.is_running = True
        self.task = asyncio.create_task(self.run())
        logger.info(f"State machine started for room {self.room_id}")

    async def stop(self):
        """Stop the state machine."""
        if not self.is_running:
            return
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info(f"State machine stopped for room {self.room_id}")

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    async def _broadcast(self, message: Dict[str, Any]) -> None:
        """Разослать сообщение всем игрокам комнаты через WebSocket.

        Безопасно обрабатывает случай, когда ws_manager не передан (тесты,
        автономный запуск), — просто логирует и не падает.
        """
        if self.ws_manager is None:
            logger.debug(
                f"ws_manager не задан для комнаты {self.room_id}; "
                f"пропуск рассылки события '{message.get('type') or message.get('event')}'"
            )
            return
        try:
            await self.ws_manager.broadcast_to_room(self.room_id, message)
        except Exception as exc:
            logger.error(
                f"Ошибка рассылки события '{message.get('type') or message.get('event')}' "
                f"в комнату {self.room_id}: {exc}"
            )

    async def _send_to_player(self, player_id: int, message: Dict[str, Any]) -> None:
        """Отправить сообщение конкретному игроку через WebSocket."""
        if self.ws_manager is None:
            logger.debug(
                f"ws_manager не задан; пропуск личного события "
                f"'{message.get('type') or message.get('event')}' "
                f"для игрока {player_id}"
            )
            return
        try:
            await self.ws_manager.send_to_player(player_id, message)
        except Exception as exc:
            logger.error(
                f"Ошибка отправки события '{message.get('type') or message.get('event')}' "
                f"игроку {player_id}: {exc}"
            )

    async def _refresh_players(self) -> None:
        """Обновить self.players свежими данными из БД."""
        result = await self.db.execute(
            select(Player).where(Player.room_id == self.room_id)
        )
        self.players = list(result.scalars().all())

    def _build_game_context(self, extra: dict = None) -> dict:
        """Строит словарь контекста игры для передачи в ai_service."""
        alive = [
            {"id": p.id, "name": p.nickname or f"Player{p.id}"}
            for p in self.players if p.is_alive
        ]
        dead = [
            {"id": p.id, "name": p.nickname or f"Player{p.id}"}
            for p in self.players if not p.is_alive
        ]
        ctx = {
            "phase": self.current_phase.value if hasattr(self.current_phase, "value") else str(self.current_phase),
            "day_number": self.day_number,
            "alive_players": alive,
            "dead_players": dead,
            "night_number": self.night_number,
            "recent_messages": self.day_chat_history[-10:],
            "day_chat_history": self.day_chat_history,
        }
        if extra:
            ctx.update(extra)
        return ctx

    async def _get_game_state_for_ai(self, player_id: int) -> dict:
        """Колбэк MCP get_game_state — возвращает сводку состояния игры."""
        return self._build_game_context()

    async def _process_ai_chat_message(self, player_id: int, content: str) -> dict:
        """Колбэк MCP send_message — обрабатывает сообщение бота в общий чат."""
        logger.info(f"_process_ai_chat_message called: player_id={player_id}, content='{content}'")
        logger.info(f"  self.players: {[(p.id, p.nickname, p.is_alive) for p in self.players]}")
        
        # Защита от дублирования: проверяем, не отправлялось ли это сообщение недавно
        current_time = time.time()
        last_msg = self.ai_last_message.get(player_id, "")
        last_time = self.ai_last_message_time.get(player_id, 0)
        
        # Если сообщение то же самое и прошло меньше 5 секунд - игнорируем
        if last_msg == content and (current_time - last_time) < 5:
            logger.warning(f"Duplicate message detected for player {player_id}: '{content}' (last sent {current_time - last_time:.1f}s ago)")
            return {"ok": True, "duplicate": True}
        
        # Обновляем трекинг
        self.ai_last_message[player_id] = content
        self.ai_last_message_time[player_id] = current_time
        
        player = next((p for p in self.players if p.id == player_id), None)
        if not player:
            logger.warning(f"Player {player_id} NOT FOUND in self.players")
            # Попробуем найти по нику
            logger.warning(f"Available players: {[(p.id, p.nickname) for p in self.players]}")
            return {"ok": False, "reason": "player not found"}
        
        if not player.is_alive:
            logger.warning(f"Player {player_id} is dead")
            return {"ok": False, "reason": "player dead"}

        msg = {
            "sender_id": player_id,
            "sender_name": player.nickname or f"Player{player_id}",
            "content": content,
            "is_ai": True,
        }
        self.day_chat_history.append(msg)

        # Сохраняем событие в БД
        if self.db and self.game_id:
            try:
                event = GameEvent(
                    game_id=self.game_id,
                    player_id=player_id,
                    event_type="chat",
                    event_data=json.dumps({"content": content, "nickname": player.nickname})
                )
                self.db.add(event)
                await self.db.commit()
            except Exception as e:
                logger.error(f"Failed to save chat event: {e}")

        # Разослать всем игрокам комнаты
        logger.info(f"Broadcasting chat message from player {player_id}: {content}")
        await self._broadcast({
            "event": "chat_message",
            "data": msg,
        })
        return {"ok": True}

    async def _process_ai_vote(self, player_id: int, target_player_id: int) -> dict:
        """Колбэк MCP vote_for_player — регистрирует голос ИИ."""
        if player_id not in self.votes:
            self.votes[player_id] = target_player_id
            player = next((p for p in self.players if p.id == player_id), None)
            
            # Сохраняем событие в БД
            if self.db and self.game_id:
                try:
                    event = GameEvent(
                        game_id=self.game_id,
                        player_id=player_id,
                        event_type="vote",
                        event_data=json.dumps({"target_player_id": target_player_id})
                    )
                    self.db.add(event)
                    await self.db.commit()
                except Exception as e:
                    logger.error(f"Failed to save vote event: {e}")
            
            await self._broadcast({
                "event": "vote_cast",
                "data": {
                    "voter_id": player_id,
                    "voter_name": (player.nickname if player else f"Player{player_id}"),
                    "target_id": target_player_id,
                },
            })
        return {"ok": True, "voted_for": target_player_id}

    async def _process_ai_night_action(
        self, player_id: int, action_type: str, target_player_id: int
    ) -> dict:
        """Колбэк MCP perform_night_action — регистрирует ночное действие ИИ.

        Сохраняем в формате совместимом с resolve_night_actions:
        {"action": ..., "target_id": ...}
        """
        self.night_actions[player_id] = {
            "action": action_type,
            "target_id": target_player_id,
        }
        
        # Сохраняем событие в БД
        if self.db and self.game_id:
            try:
                event = GameEvent(
                    game_id=self.game_id,
                    player_id=player_id,
                    event_type="night_action",
                    event_data=json.dumps({"action_type": action_type, "target_player_id": target_player_id})
                )
                self.db.add(event)
                await self.db.commit()
            except Exception as e:
                logger.error(f"Failed to save night action event: {e}")
        
        return {"ok": True, "action": action_type, "target": target_player_id}

    # ------------------------------------------------------------------
    # Главный цикл
    # ------------------------------------------------------------------

    async def run(self):
        """Main state machine loop."""
        try:
            while self.is_running:
                if self.current_phase == GamePhase.LOBBY:
                    await self.handle_lobby()
                elif self.current_phase == GamePhase.ROLE_ASSIGNMENT:
                    await self.handle_role_assignment()
                elif self.current_phase == GamePhase.NIGHT:
                    await self.handle_night()
                elif self.current_phase == GamePhase.DAY:
                    await self.handle_day()
                elif self.current_phase == GamePhase.VOTING:
                    await self.handle_voting()
                elif self.current_phase == GamePhase.TURING_TEST:
                    # Тест Тьюринга — ожидаем голосов или принудительного завершения по таймеру
                    await asyncio.sleep(1)
                elif self.current_phase == GamePhase.FINISHED:
                    await self.handle_finished()
                    break
                else:
                    logger.warning(f"Unknown phase: {self.current_phase}")
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info(f"State machine cancelled for room {self.room_id}")
        except Exception as e:
            logger.error(f"Error in state machine for room {self.room_id}: {e}", exc_info=True)
        finally:
            self.is_running = False

    # ------------------------------------------------------------------
    # Фазы игры
    # ------------------------------------------------------------------

    async def handle_lobby(self):
        """Фаза лобби — ожидаем сигнала старта игры."""
        await self._broadcast({"event": "phase_changed", "data": {"phase": "lobby"}})
        
        # Проверяем, была ли игра уже запущена (через game_service)
        # Если игра уже началась (есть game_id), сразу переходим к ROLE_ASSIGNMENT
        if self.game_id:
            logger.info(f"Game already started for room {self.room_id}, transitioning to ROLE_ASSIGNMENT")
            self.current_phase = GamePhase.ROLE_ASSIGNMENT
            return
        
        # Иначе ожидаем сигнала старта игры от хоста
        await asyncio.sleep(1)

    async def handle_role_assignment(self):
        """Назначить роли игрокам и инициализировать игру."""
        logger.info(f"Assigning roles for room {self.room_id}")
        room = await self.db.get(Room, self.room_id)
        if not room:
            logger.error(f"Room {self.room_id} not found")
            await self.stop()
            return

        # Получить всех игроков комнаты
        result = await self.db.execute(select(Player).where(Player.room_id == self.room_id))
        players = list(result.scalars().all())
        if not players:
            logger.error(f"No players found for room {self.room_id}")
            await self.stop()
            return

        # Сохраняем список игроков в памяти
        self.players = players

        # Распределение ролей: 1 мафия на каждые 3 игрока, 1 доктор, 1 комиссар
        num_players = len(players)
        num_mafia = max(1, num_players // 3)
        num_doctors = 1 if num_players >= 4 else 0
        num_commissioners = 1 if num_players >= 5 else 0
        num_civilians = num_players - num_mafia - num_doctors - num_commissioners

        roles = (
            [PlayerRole.MAFIA] * num_mafia
            + [PlayerRole.DOCTOR] * num_doctors
            + [PlayerRole.COMMISSIONER] * num_commissioners
            + [PlayerRole.CIVILIAN] * num_civilians
        )
        random.shuffle(roles)

        for player, role in zip(players, roles):
            player.role = role
            self.db.add(player)
        await self.db.commit()

        # Создать запись игры
        game = Game(
            room_id=self.room_id,
            status=GameStatus.NIGHT,
            day_number=1,
        )
        self.db.add(game)
        await self.db.commit()
        self.game_id = game.id

        # Уведомить каждого игрока о его роли персональным сообщением
        for player in players:
            logger.info(f"Player {player.id} ({player.nickname}) assigned role {player.role}")
            await self._send_to_player(
                player.id,
                {
                    "type": "role_assigned",
                    "player_id": player.id,
                    "role": player.role.value if player.role else None,
                    "day_number": self.day_number,
                    "message": f"Ваша роль: {player.role.value if player.role else 'unknown'}",
                },
            )

        self.current_phase = GamePhase.NIGHT
        await self.update_game_status(GameStatus.NIGHT)

    async def handle_night(self) -> None:
        """Фаза ночи — ИИ-игроки выполняют ночные действия."""
        self.night_number += 1
        self.night_actions = {}

        logger.info(
            f"Starting night phase for room {self.room_id}, night {self.night_number}"
        )

        # Обновляем список игроков (актуальный is_alive)
        await self._refresh_players()

        await self._broadcast(
            {
                "event": "phase_changed",
                "data": {
                    "phase": "night",
                    "night_number": self.night_number,
                },
            }
        )
        # Обратная совместимость — старый тип события
        await self._broadcast(
            {
                "type": "night_started",
                "phase": GamePhase.NIGHT.value,
                "day_number": self.day_number,
                "message": "Наступила ночь. Мафия, доктор и комиссар выбирают жертв...",
            }
        )

        # Внешний страховочный таймер — принудительно завершит ночь если истечёт
        if self.game_service:
            self.game_service.start_phase_timer(self.room_id, "night")

        # Разделяем ИИ-игроков по ролям
        ai_players = [p for p in self.players if p.is_ai and p.is_alive]
        mafia_ai = [p for p in ai_players if p.role == PlayerRole.MAFIA]
        doctor_ai = [p for p in ai_players if p.role == PlayerRole.DOCTOR]
        commissioner_ai = [p for p in ai_players if p.role == PlayerRole.COMMISSIONER]

        if self.ai_service and self.mcp_dispatcher:
            context = self._build_game_context({"phase": "night"})
            tasks: List[Any] = []

            for player in mafia_ai:
                ctx = {
                    **context,
                    "phase": "night",
                    "your_role": "mafia",
                    "instruction": "Choose a civilian to kill tonight.",
                }
                tasks.append(
                    self.ai_service.request_night_action(player, ctx, self.mcp_dispatcher)
                )

            for player in doctor_ai:
                ctx = {
                    **context,
                    "phase": "night",
                    "your_role": "doctor",
                    "instruction": "Choose a player to heal/protect tonight.",
                }
                tasks.append(
                    self.ai_service.request_night_action(player, ctx, self.mcp_dispatcher)
                )

            for player in commissioner_ai:
                ctx = {
                    **context,
                    "phase": "night",
                    "your_role": "detective",
                    "instruction": "Choose a player to investigate their alignment.",
                }
                tasks.append(
                    self.ai_service.request_night_action(player, ctx, self.mcp_dispatcher)
                )

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for idx, res in enumerate(results):
                    if isinstance(res, Exception):
                        logger.error(f"AI night action error (task {idx}): {res}")
                        # Fallback для каждой роли при ошибке
                        player = None
                        if idx < len(mafia_ai):
                            player = mafia_ai[idx]
                            alive_non_mafia = [p for p in self.players if p.is_alive and p.role != PlayerRole.MAFIA]
                            if alive_non_mafia:
                                target = random.choice(alive_non_mafia)
                                self.night_actions[player.id] = {"action": "kill", "target_id": target.id}
                        elif idx < len(mafia_ai) + len(doctor_ai):
                            player = doctor_ai[idx - len(mafia_ai)]
                            alive_all = [p for p in self.players if p.is_alive]
                            if alive_all:
                                target = random.choice(alive_all)
                                self.night_actions[player.id] = {"action": "heal", "target_id": target.id}
                        else:
                            player = commissioner_ai[idx - len(mafia_ai) - len(doctor_ai)]
                            non_self = [p for p in self.players if p.is_alive and p.id != player.id]
                            if non_self:
                                target = random.choice(non_self)
                                self.night_actions[player.id] = {"action": "investigate", "target_id": target.id}
        else:
            # Fallback: случайный выбор если ai_service не подключён
            alive_non_mafia = [
                p for p in self.players if p.is_alive and p.role != PlayerRole.MAFIA
            ]
            alive_all = [p for p in self.players if p.is_alive]

            for player in mafia_ai:
                if alive_non_mafia:
                    target = random.choice(alive_non_mafia)
                    self.night_actions[player.id] = {
                        "action": "kill",
                        "target_id": target.id,
                    }

            for player in doctor_ai:
                if alive_all:
                    target = random.choice(alive_all)
                    self.night_actions[player.id] = {
                        "action": "heal",
                        "target_id": target.id,
                    }

            for player in commissioner_ai:
                non_self = [p for p in alive_all if p.id != player.id]
                if non_self:
                    target = random.choice(non_self)
                    self.night_actions[player.id] = {
                        "action": "investigate",
                        "target_id": target.id,
                    }

        # Если все ночные роли — ИИ, небольшая реалистичная пауза
        human_night_players = [
            p for p in self.players
            if not p.is_ai and p.is_alive
            and p.role in (PlayerRole.MAFIA, PlayerRole.DOCTOR, PlayerRole.COMMISSIONER)
        ]
        if not human_night_players:
            await asyncio.sleep(2)

        await self.resolve_night_actions()

        # Переход в дневную фазу только если игра ещё не завершена
        if self.current_phase not in (GamePhase.FINISHED, GamePhase.TURING_TEST):
            self.current_phase = GamePhase.DAY
            await self.update_game_status(GameStatus.DAY)

    async def resolve_night_actions(self) -> None:
        """Resolve the night actions and update player states."""
        logger.info(f"Resolving night actions for room {self.room_id}")

        killed_by_mafia: Set[int] = set()
        healed_by_doctor: Set[int] = set()
        # commissioner_id -> {target_id, is_mafia}
        investigated_results: Dict[int, Dict[str, Any]] = {}

        # Итерируемся по парам player_id -> action, чтобы знать, кто комиссар
        for actor_id, action in self.night_actions.items():
            if action["action"] == "kill":
                killed_by_mafia.add(action["target_id"])
            elif action["action"] == "heal":
                healed_by_doctor.add(action["target_id"])
            elif action["action"] == "investigate":
                target_id: int = action["target_id"]
                target: Optional[Player] = await self.db.get(Player, target_id)
                if target:
                    investigated_results[actor_id] = {
                        "target_id": target_id,
                        "target_nickname": target.nickname,
                        "is_mafia": target.role == PlayerRole.MAFIA,
                    }

        # Определяем действительно убитых: убиты мафией, но не вылечены доктором
        actually_killed: Set[int] = killed_by_mafia - healed_by_doctor

        # Собираем информацию об убитых игроках для night_summary
        killed_details: List[Dict[str, Any]] = []
        for player_id in actually_killed:
            player: Optional[Player] = await self.db.get(Player, player_id)
            if player:
                player.is_alive = False
                self.db.add(player)
                # Переводим убитого игрока в Ghost Chat
                if self.ws_manager:
                    await self.ws_manager.move_to_ghost(self.room_id, player.id)
                killed_details.append(
                    {"player_id": player.id, "nickname": player.nickname}
                )
                logger.info(
                    f"Player {player_id} ({player.nickname}) was killed during the night"
                )

        # Информация о вылеченных
        healed_details: List[Dict[str, Any]] = []
        for player_id in healed_by_doctor:
            player = await self.db.get(Player, player_id)
            if player:
                healed_details.append(
                    {"player_id": player.id, "nickname": player.nickname}
                )

        await self.db.commit()

        # Сохраняем итоги ночи для рассылки при наступлении дня
        self.night_summary = {
            "day_number": self.day_number,
            "killed": killed_details,
            "healed": healed_details,
        }

        # Отправляем результат расследования лично каждому комиссару
        for commissioner_id, result in investigated_results.items():
            logger.info(
                f"Commissioner {commissioner_id} investigated player {result['target_id']}: "
                f"is_mafia={result['is_mafia']}"
            )
            await self._send_to_player(
                commissioner_id,
                {
                    "type": "investigation_result",
                    "target_id": result["target_id"],
                    "target_nickname": result["target_nickname"],
                    "is_mafia": result["is_mafia"],
                    "day_number": self.day_number,
                },
            )

        # Обновляем in-memory список игроков после смертей
        await self._refresh_players()

        # Проверяем условие конца игры
        await self.check_game_over()

    async def handle_day(self) -> None:
        """Фаза дня — обсуждение перед голосованием."""
        self.day_chat_history = []  # Сбрасываем историю нового дня

        logger.info(f"Starting day phase for room {self.room_id}, day {self.day_number}")

        await self._refresh_players()

        # Рассылаем итоги ночи всем игрокам
        await self._broadcast(
            {
                "type": "day_started",
                "event": "phase_changed",
                "phase": GamePhase.DAY.value,
                "data": {"phase": "day", "day_number": self.night_number},
                "day_number": self.night_summary.get("day_number", self.day_number),
                "night_results": {
                    "killed": self.night_summary.get("killed", []),
                    "healed": self.night_summary.get("healed", []),
                },
                "message": "Наступил день. Обсудите произошедшее и проголосуйте за подозреваемого.",
            }
        )

        # Внешний страховочный таймер — принудительно завершит день если истечёт
        if self.game_service:
            self.game_service.start_phase_timer(self.room_id, "day")

        if self.ai_service and self.mcp_dispatcher:
            # Запускаем дневной чат ботов в фоне с реалистичными задержками
            asyncio.create_task(self._run_ai_day_chat())
            # Ждём время обсуждения (30 секунд) пока боты общаются в фоне
            await asyncio.sleep(30)
        else:
            # Заглушка: просто ждём 5 секунд
            await asyncio.sleep(5)

        # Уведомить о начале фазы голосования
        await self._broadcast(
            {
                "type": "voting_started",
                "event": "phase_changed",
                "phase": GamePhase.VOTING.value,
                "data": {"phase": "voting"},
                "day_number": self.day_number,
                "message": "Время голосовать! Выберите игрока для исключения.",
            }
        )

        # Переход в фазу голосования
        self.current_phase = GamePhase.VOTING
        await self.update_game_status(GameStatus.VOTING)

    async def _run_ai_day_chat(self) -> None:
        """Запускает дневной чат ботов с реалистичными задержками."""
        logger.info(f"_run_ai_day_chat START: players count = {len(self.players)}")
        ai_alive = [p for p in self.players if p.is_ai and p.is_alive]
        logger.info(f"  AI alive players: {[(p.id, p.nickname) for p in ai_alive]}")
        
        if not ai_alive:
            logger.info("  No AI alive players, returning")
            return

        # 3 раунда диалога с рандомными задержками
        for round_num in range(3):
            # Задержка между раундами (5-15 секунд, уменьшена для реализма в 30с окне)
            await asyncio.sleep(random.uniform(3, 8))

            # Перемешиваем порядок ботов и берём случайное подмножество
            bots_this_round = random.sample(
                ai_alive, k=min(len(ai_alive), random.randint(1, len(ai_alive)))
            )

            for bot in bots_this_round:
                # Проверяем что бот ещё жив
                if not bot.is_alive:
                    continue

                # Индикатор набора текста
                await self._broadcast(
                    {"event": "typing_indicator", "data": {"player_id": bot.id, "typing": True}}
                )

                # Задержка "печатания" (2-5 секунд)
                await asyncio.sleep(random.uniform(2, 5))

                ctx = self._build_game_context({"phase": "day"})
                logger.info(f"Calling AI service for player {bot.id} ({bot.nickname})")
                logger.info(f"  ai_service: {self.ai_service}")
                logger.info(f"  mcp_dispatcher: {self.mcp_dispatcher}")
                
                try:
                    result = await self.ai_service.request_day_message(bot, ctx, self.mcp_dispatcher)
                    logger.info(f"AI day message result for player {bot.id}: {result}")
                    
                    # Если результат пустой или ошибка - используем fallback
                    if not result or result.get("error"):
                        raise Exception(f"AI returned error or empty result: {result}")
                except Exception as e:
                    # Увеличиваем счётчик ошибок для этого бота
                    self.ai_error_counts[bot.id] = self.ai_error_counts.get(bot.id, 0) + 1
                    error_count = self.ai_error_counts[bot.id]
                    
                    logger.error(f"AI day message error (player_id={bot.id}, error_count={error_count}): {e}")
                    
                    # Fallback: отправляем разнообразное сообщение если API недоступен
                    # Добавляем больше разнообразных сообщений для разных ролей
                    fallback_messages = [
                        # Общие сообщения
                        "Интересно, кто же мафия?",
                        "Нужно внимательнее следить за поведением игроков.",
                        "Я доверяю этому игроку.",
                        "Давайте обсудим кандидатов.",
                        "Кто-то ведёт себя подозрительно.",
                        "Я мирный житель, не голосуйте за меня.",
                        "Нужно больше информации.",
                        "Слушаю ваши аргументы.",
                        # Дополнительные сообщения для разнообразия
                        "Интересная точка зрения, нужно подумать.",
                        "Я пока не определился, давайте послушаем других.",
                        "Обратите внимание на поведение этого игрока.",
                        "Мне кажется, мы что-то упускаем.",
                        "Нужно голосовать внимательнее.",
                        "Кто-то явно нервничает.",
                        "Давайте соберём больше фактов.",
                        "Я слежу за реакциями игроков.",
                        "Пока слишком рано делать выводы.",
                        "Нужно выслушать все мнения.",
                    ]
                    
                    # Получаем последнее использованное сообщение этого бота
                    last_msg = self.ai_last_fallback.get(bot.id, "")
                    
                    # Фильтруем: исключаем последнее использованное сообщение
                    available_messages = [m for m in fallback_messages if m != last_msg]
                    
                    # Если все сообщения были использованы (маловероятно), сбрасываем
                    if not available_messages:
                        available_messages = fallback_messages.copy()
                    
                    # Выбираем случайное сообщение из доступных
                    fallback_msg = random.choice(available_messages)
                    
                    # Сохраняем для следующего раза
                    self.ai_last_fallback[bot.id] = fallback_msg
                    
                    logger.info(f"AI fallback message for player {bot.id} (error #{error_count}): {fallback_msg}")
                    await self._process_ai_chat_message(bot.id, fallback_msg)

                await self._broadcast(
                    {"event": "typing_indicator", "data": {"player_id": bot.id, "typing": False}}
                )

                # Пауза между сообщениями разных ботов
                await asyncio.sleep(random.uniform(1, 3))

    async def handle_voting(self) -> None:
        """Фаза голосования — игроки голосуют за исключение подозреваемого."""
        logger.info(f"Starting voting phase for room {self.room_id}, day {self.day_number}")

        self.votes = {}
        await self._refresh_players()

        await self._broadcast(
            {
                "event": "phase_changed",
                "type": "voting_started",
                "data": {"phase": "voting"},
                "day_number": self.day_number,
                "message": "Голосование началось! Выберите игрока для исключения.",
            }
        )

        # Внешний страховочный таймер — принудительно завершит голосование если истечёт
        if self.game_service:
            self.game_service.start_phase_timer(self.room_id, "voting")

        if self.ai_service and self.mcp_dispatcher:
            ai_alive = [p for p in self.players if p.is_ai and p.is_alive]

            vote_tasks = [
                self._ai_vote_with_delay(bot, self._build_game_context({"phase": "voting"}))
                for bot in ai_alive
            ]

            if vote_tasks:
                await asyncio.gather(*vote_tasks, return_exceptions=True)
        else:
            # Fallback: случайное голосование
            for player in self.players:
                if player.is_ai and player.is_alive:
                    targets = [p for p in self.players if p.is_alive and p.id != player.id]
                    if targets:
                        target = random.choice(targets)
                        self.votes[player.id] = target.id

        # Ждём голосов живых людей если они есть
        human_alive = [p for p in self.players if not p.is_ai and p.is_alive]
        if not human_alive:
            await asyncio.sleep(2)

        # Финализируем голосование (подсчёт + выбывание + переход к ночи)
        await self._finalize_voting()

    async def _finalize_voting(self) -> None:
        """
        Подсчитать голоса, применить выбывание, проверить конец игры.
        Вызывается как из handle_voting (нормальный путь), так и из
        force_advance_phase (принудительное завершение по таймеру).
        """
        # ── Подсчёт голосов и выбывание ─────────────────────────────────────
        vote_counts: Dict[int, int] = {}
        for voter_id, target_id in self.votes.items():
            vote_counts[target_id] = vote_counts.get(target_id, 0) + 1

        eliminated_id: Optional[int] = None
        if vote_counts:
            max_target_id = max(vote_counts, key=vote_counts.get)
            max_votes = vote_counts[max_target_id]
            # Ничья — никто не выбывает
            if list(vote_counts.values()).count(max_votes) > 1:
                logger.info("Vote resulted in a tie, no elimination")
            else:
                eliminated_id = max_target_id
                logger.info(
                    f"Player {eliminated_id} received {max_votes} votes and is eliminated"
                )

        if eliminated_id is not None:
            player = await self.db.get(Player, eliminated_id)
            if player:
                player.is_alive = False
                self.db.add(player)
                # Переводим выбывшего в Ghost Chat
                if self.ws_manager:
                    await self.ws_manager.move_to_ghost(self.room_id, player.id)
                logger.info(
                    f"Player {eliminated_id} ({player.nickname}) was eliminated during voting"
                )
                await self._broadcast(
                    {
                        "event": "player_eliminated",
                        "type": "player_eliminated",
                        "data": {
                            "player_id": eliminated_id,
                            "nickname": player.nickname,
                            "role": player.role.value if player.role else None,
                        },
                    }
                )

        await self.db.commit()
        await self._refresh_players()

        # Инкремент дня и проверка конца игры
        self.day_number += 1
        await self.check_game_over()

        # Если игра не завершена и не в Тесте Тьюринга — переходим к ночи
        if self.current_phase not in (GamePhase.FINISHED, GamePhase.TURING_TEST):
            self.current_phase = GamePhase.NIGHT
            await self.update_game_status(GameStatus.NIGHT)
            if self.game_service:
                self.game_service.start_phase_timer(self.room_id, "night")

    async def _ai_vote_with_delay(self, player: Any, context: dict) -> None:
        """Запрашивает голос у ИИ с небольшой случайной задержкой."""
        await asyncio.sleep(random.uniform(2, 8))
        try:
            await self.ai_service.request_vote(player, context, self.mcp_dispatcher)
        except Exception as e:
            logger.error(f"AI vote error (player_id={player.id}): {e}")
            # Fallback: случайный голос
            targets = [p for p in self.players if p.is_alive and p.id != player.id]
            if targets:
                target = random.choice(targets)
                self.votes[player.id] = target.id

    async def force_advance_phase(self) -> None:
        """
        Принудительно завершить текущую фазу и перейти к следующей.
        Вызывается таймером из game_service когда время фазы истекло.
        """
        phase_val = (
            self.current_phase.value
            if hasattr(self.current_phase, "value")
            else str(self.current_phase)
        )
        logger.info(
            f"Force advancing phase '{phase_val}' for room {self.room_id}"
        )

        if self.current_phase == GamePhase.NIGHT:
            # Принудительно завершаем ночь — запускаем resolve с имеющимися действиями
            await self.resolve_night_actions()
            # Переход в дневную фазу (resolve не переключает сам)
            if self.current_phase != GamePhase.FINISHED:
                self.current_phase = GamePhase.DAY
                await self.update_game_status(GameStatus.DAY)

        elif self.current_phase == GamePhase.DAY:
            # Принудительно завершаем обсуждение — переходим к голосованию
            self.current_phase = GamePhase.VOTING
            await self.update_game_status(GameStatus.VOTING)
            await self._broadcast(
                {
                    "event": "phase_changed",
                    "type": "voting_started",
                    "data": {"phase": "voting"},
                    "day_number": self.day_number,
                    "message": "Время обсуждения истекло. Голосование началось!",
                }
            )
            if self.game_service:
                self.game_service.start_phase_timer(self.room_id, "voting")

        elif self.current_phase == GamePhase.VOTING:
            # Принудительно завершаем голосование — считаем с тем что есть
            await self._finalize_voting()

        elif self.current_phase == GamePhase.TURING_TEST:
            # Принудительно завершаем Тест Тьюринга по таймеру
            await self._finish_turing_test()

        elif self.current_phase == GamePhase.LOBBY:
            logger.info(
                f"force_advance_phase called during LOBBY for room {self.room_id}, ignoring"
            )

    # ------------------------------------------------------------------
    # Тест Тьюринга
    # ------------------------------------------------------------------

    async def _start_turing_test(self) -> None:
        """Запустить фазу Теста Тьюринга после окончания игры."""
        self.current_phase = GamePhase.TURING_TEST
        self.turing_votes = {}

        # Формируем список всех игроков (включая мёртвых), НЕ раскрывая is_ai
        all_players_info = [
            {
                "id": p.id,
                "name": p.nickname or f"Player{p.id}",
                "is_alive": p.is_alive,
            }
            for p in self.players
        ]

        payload = {
            "event": "turing_test_started",
            "data": {
                "message": "The game is over! Now guess which players were AI bots.",
                "players": all_players_info,
                "duration_seconds": 90,
                "instruction": (
                    "Vote for the players you think were AI bots. "
                    "You can vote for multiple players."
                ),
            },
        }

        # Рассылаем и живым, и призракам
        await self._broadcast(payload)
        if self.ws_manager:
            await self.ws_manager.broadcast_to_ghosts(self.room_id, payload)

        # Обновляем фазу в БД
        await self.update_game_status(GameStatus.TURING_TEST)

        # Запускаем страховочный таймер Теста Тьюринга
        if self.game_service:
            self.game_service.start_phase_timer(self.room_id, "turing_test")

        logger.info(f"Turing test started for room {self.room_id}")

    async def _handle_turing_test_vote(
        self, voter_id: int, suspected_ai_ids: List[int]
    ) -> None:
        """
        Обработать голос игрока в Тесте Тьюринга.

        Args:
            voter_id: ID игрока, который голосует
            suspected_ai_ids: список ID игроков, которых он считает ИИ
        """
        for suspect_id in suspected_ai_ids:
            if suspect_id not in self.turing_votes:
                self.turing_votes[suspect_id] = []
            if voter_id not in self.turing_votes[suspect_id]:
                self.turing_votes[suspect_id].append(voter_id)

        # Подтверждаем голос голосующему
        if self.ws_manager:
            await self.ws_manager.send_to_player(
                voter_id,
                {
                    "event": "turing_vote_accepted",
                    "data": {"suspected_ai_ids": suspected_ai_ids},
                },
            )
        logger.info(
            f"Turing vote from player {voter_id}: suspects {suspected_ai_ids}"
        )

    def _calculate_humanness_scores(self) -> Dict[int, float]:
        """
        Вычислить «метрику человечности» для каждого ИИ-игрока.

        Формула: humanness = 1 - (votes_received / max_possible_votes)
        1.0 — никто не заподозрил (идеально «человечный» ИИ)
        0.0 — все заподозрили (очевидный ИИ)
        """
        total_players = len(self.players)
        scores: Dict[int, float] = {}

        for p in self.players:
            if not getattr(p, "is_ai", False):
                continue
            votes_received = len(self.turing_votes.get(p.id, []))
            max_votes = total_players - 1  # нельзя голосовать за себя
            if max_votes <= 0:
                scores[p.id] = 1.0
            else:
                humanness = 1.0 - (votes_received / max_votes)
                scores[p.id] = round(max(0.0, min(1.0, humanness)), 3)

        return scores

    async def _finish_turing_test(self) -> None:
        """Завершить Тест Тьюринга: подсчитать результаты и сохранить в БД."""
        from app.crud import game as game_crud

        # Отменяем таймер Тьюринга
        if self.game_service:
            self.game_service.cancel_phase_timer(self.room_id)

        humanness_scores = self._calculate_humanness_scores()

        # Раскрываем реальные роли и результаты
        reveal_data = [
            {
                "id": p.id,
                "name": p.nickname or f"Player{p.id}",
                "is_ai": getattr(p, "is_ai", False),
                "role": p.role.value if p.role else "unknown",
                "humanness_score": humanness_scores.get(p.id),  # None для людей
                "votes_against": len(self.turing_votes.get(p.id, [])),
            }
            for p in self.players
        ]

        result_payload = {
            "event": "turing_test_results",
            "data": {
                "reveal": reveal_data,
                "turing_votes": {str(k): v for k, v in self.turing_votes.items()},
                "humanness_scores": {str(k): v for k, v in humanness_scores.items()},
                "message": "Here are the true identities of all players!",
            },
        }

        # Рассылаем результаты и живым, и призракам
        await self._broadcast(result_payload)
        if self.ws_manager:
            await self.ws_manager.broadcast_to_ghosts(self.room_id, result_payload)

        # Сохраняем в БД
        if self.game_id:
            try:
                await game_crud.save_turing_results(
                    db=self.db,
                    game_id=self.game_id,
                    turing_votes={str(k): v for k, v in self.turing_votes.items()},
                    humanness_scores={str(k): v for k, v in humanness_scores.items()},
                )
            except Exception as e:
                logger.error(f"Failed to save turing results for game {self.game_id}: {e}")

        # Переходим в FINISHED
        self.current_phase = GamePhase.FINISHED
        await self._broadcast(
            {
                "event": "game_finished",
                "data": {"winner": self.winner},
            }
        )
        await self.update_game_status(GameStatus.FINISHED)
        logger.info(f"Turing test finished for room {self.room_id}")

    async def handle_finished(self) -> None:
        """Фаза завершения игры — логирование и остановка."""
        logger.info(f"Game finished for room {self.room_id}")
        self.is_running = False

    async def check_game_over(self) -> None:
        """Проверить условия завершения игры и установить фазу FINISHED."""
        result = await self.db.execute(
            select(Player).where(Player.room_id == self.room_id, Player.is_alive == True)
        )
        alive_players = result.scalars().all()
        alive_mafia: List[Player] = [p for p in alive_players if p.role == PlayerRole.MAFIA]
        alive_civilians: List[Player] = [p for p in alive_players if p.role != PlayerRole.MAFIA]

        # Условия конца игры:
        # 1. Вся мафия мертва → мирные победили
        # 2. Мафия >= мирных → мафия победила
        winner: Optional[str]
        if not alive_mafia:
            logger.info(f"Game over: all mafia are dead. Civilians win in room {self.room_id}")
            winner = "civilians"
        elif len(alive_mafia) >= len(alive_civilians):
            logger.info(
                f"Game over: mafia outnumber or equal civilians. Mafia wins in room {self.room_id}"
            )
            winner = "mafia"
        else:
            return

        self.winner = winner

        if self.game_id:
            game: Optional[Game] = await self.db.get(Game, self.game_id)
            if game:
                game.winner = winner
                self.db.add(game)
                await self.db.commit()

        logger.info(f"Game finished in room {self.room_id}. Winner: {winner}")

        # Раскрываем роли ВСЕХ игроков (включая мёртвых) для финального экрана
        all_result = await self.db.execute(
            select(Player).where(Player.room_id == self.room_id)
        )
        all_players: List[Player] = list(all_result.scalars().all())
        reveal_players: List[Dict[str, Any]] = [
            {
                "player_id": p.id,
                "nickname": p.nickname,
                "role": p.role.value if p.role else None,
                "is_alive": p.is_alive,
            }
            for p in all_players
        ]
        await self._broadcast(
            {
                "type": "game_over",
                "event": "game_over",
                "data": {"winner": winner},
                "winner": winner,
                "day_number": self.day_number,
                "players": reveal_players,
                "message": (
                    "Мирные жители победили! Мафия уничтожена."
                    if winner == "civilians"
                    else "Мафия победила! Она взяла город под контроль."
                ),
            }
        )
        
        # Запускаем Тест Тьюринга вместо прямого перехода в FINISHED
        await self._start_turing_test()

    async def update_game_status(self, status: GameStatus) -> None:
        """Обновить статус игры в базе данных."""
        if self.game_id:
            game = await self.db.get(Game, self.game_id)
            if game:
                game.status = status
                self.db.add(game)
                await self.db.commit()
        # Обновляем статус комнаты при необходимости
        room = await self.db.get(Room, self.room_id)
        if room and status in [GameStatus.NIGHT, GameStatus.DAY, GameStatus.VOTING]:
            if room.status == RoomStatus.LOBBY:
                room.status = RoomStatus.PLAYING
                self.db.add(room)
                await self.db.commit()
