import asyncio
import random
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set
from app.models.room import Room
from app.models.player import Player, PlayerRole
from app.models.game import Game, GameStatus
from app.models.game_event import GameEvent
from app.db.session import AsyncSession
from sqlalchemy import select, update
import json
import logging

if TYPE_CHECKING:
    from app.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)


class GamePhase(str, Enum):
    LOBBY = "lobby"
    ROLE_ASSIGNMENT = "role_assignment"
    NIGHT = "night"
    DAY = "day"
    VOTING = "voting"
    FINISHED = "finished"


class StateMachine:
    def __init__(
        self,
        room_id: int,
        db: AsyncSession,
        ws_manager: Optional["ConnectionManager"] = None,
    ) -> None:
        self.room_id = room_id
        self.db = db
        self.ws_manager = ws_manager
        self.current_phase = GamePhase.LOBBY
        self.game_id: Optional[int] = None
        self.night_actions: Dict[int, Dict[str, Any]] = {}  # player_id -> action
        self.votes: Dict[int, int] = {}  # voter_id -> target_player_id
        self.day_number: int = 1
        self.is_running: bool = False
        self.task: Optional[asyncio.Task] = None
        # Итоги последней ночи для рассылки в начале дня
        self.night_summary: Dict[str, Any] = {}

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
                f"пропуск рассылки события '{message.get('type')}'"
            )
            return
        try:
            await self.ws_manager.broadcast_to_room(self.room_id, message)
        except Exception as exc:
            logger.error(
                f"Ошибка рассылки события '{message.get('type')}' "
                f"в комнату {self.room_id}: {exc}"
            )

    async def _send_to_player(self, player_id: int, message: Dict[str, Any]) -> None:
        """Отправить сообщение конкретному игроку через WebSocket."""
        if self.ws_manager is None:
            logger.debug(
                f"ws_manager не задан; пропуск личного события '{message.get('type')}' "
                f"для игрока {player_id}"
            )
            return
        try:
            await self.ws_manager.send_to_player(player_id, message)
        except Exception as exc:
            logger.error(
                f"Ошибка отправки события '{message.get('type')}' "
                f"игроку {player_id}: {exc}"
            )

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
                elif self.current_phase == GamePhase.FINISHED:
                    await self.handle_finished()
                    break
                else:
                    logger.warning(f"Unknown phase: {self.current_phase}")
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info(f"State machine cancelled for room {self.room_id}")
        except Exception as e:
            logger.error(f"Error in state machine for room {self.room_id}: {e}")
        finally:
            self.is_running = False

    async def handle_lobby(self):
        """Handle the lobby phase: wait for players to join."""
        # In a real implementation, we would wait for a start signal or enough players.
        # For now, we'll just sleep and check for start condition.
        await asyncio.sleep(1)
        # Check if the game should start (e.g., host sent start_game or enough players)
        # This is a placeholder; actual trigger would come from WebSocket or API.
        # We'll transition to role assignment when the game starts.
        pass

    async def handle_role_assignment(self):
        """Assign roles to players and initialize the game."""
        logger.info(f"Assigning roles for room {self.room_id}")
        # Get the room and players
        room = await self.db.get(Room, self.room_id)
        if not room:
            logger.error(f"Room {self.room_id} not found")
            await self.stop()
            return

        # Get all players in the room
        result = await self.db.execute(select(Player).where(Player.room_id == self.room_id))
        players = result.scalars().all()
        if not players:
            logger.error(f"No players found for room {self.room_id}")
            await self.stop()
            return

        # Determine number of mafia, doctors, commissioners based on player count
        # Simple distribution: 1 mafia per 3 players, 1 doctor, 1 commissioner, rest civilians
        num_players = len(players)
        num_mafia = max(1, num_players // 3)
        num_doctors = 1 if num_players >= 4 else 0
        num_commissioners = 1 if num_players >= 5 else 0
        num_civilians = num_players - num_mafia - num_doctors - num_commissioners

        # Create a list of roles
        roles = (
            [PlayerRole.MAFIA] * num_mafia
            + [PlayerRole.DOCTOR] * num_doctors
            + [PlayerRole.COMMISSIONER] * num_commissioners
            + [PlayerRole.CIVILIAN] * num_civilians
        )
        # Shuffle the roles
        random.shuffle(roles)

        # Assign roles to players
        for player, role in zip(players, roles):
            player.role = role
            self.db.add(player)
        await self.db.commit()

        # Create a new game entry
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

        # Transition to night phase
        self.current_phase = GamePhase.NIGHT
        await self.update_game_status(GameStatus.NIGHT)

    async def handle_night(self) -> None:
        """Handle the night phase: perform night actions."""
        logger.info(f"Starting night phase for room {self.room_id}, day {self.day_number}")

        # ── Уведомить всех игроков о начале ночной фазы ──────────────────────
        await self._broadcast(
            {
                "type": "night_started",
                "phase": GamePhase.NIGHT.value,
                "day_number": self.day_number,
                "message": "Наступила ночь. Мафия, доктор и комиссар выбирают жертв...",
            }
        )

        # In a real game, we would:
        # 1. Ask mafia to choose a victim
        # 2. Ask doctor to choose a player to heal
        # 3. Ask commissioner to choose a player to investigate
        # 4. Resolve the actions
        # For simplicity, we'll simulate AI actions and then move to day.

        # Get alive players
        result = await self.db.execute(
            select(Player).where(Player.room_id == self.room_id, Player.is_alive == True)
        )
        alive_players = result.scalars().all()

        # Reset night actions
        self.night_actions = {}

        # For each alive player with a night role, simulate an action
        for player in alive_players:
            if player.role == PlayerRole.MAFIA:
                # Mafia chooses a random victim (not themselves)
                possible_targets = [p for p in alive_players if p.id != player.id]
                if possible_targets:
                    target = random.choice(possible_targets)
                    self.night_actions[player.id] = {
                        "action": "kill",
                        "target_id": target.id
                    }
            elif player.role == PlayerRole.DOCTOR:
                # Doctor chooses a random player to heal (could be themselves)
                target = random.choice(alive_players)
                self.night_actions[player.id] = {
                    "action": "heal",
                    "target_id": target.id
                }
            elif player.role == PlayerRole.COMMISSIONER:
                # Commissioner chooses a random player to investigate
                target = random.choice(alive_players)
                self.night_actions[player.id] = {
                    "action": "investigate",
                    "target_id": target.id
                }

        # Resolve night actions
        await self.resolve_night_actions()

        # After resolving, transition to day phase
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

        # Determine who actually dies: killed by mafia and not healed
        actually_killed: Set[int] = killed_by_mafia - healed_by_doctor

        # Собираем информацию о убитых игроках для night_summary
        killed_details: List[Dict[str, Any]] = []
        for player_id in actually_killed:
            player: Optional[Player] = await self.db.get(Player, player_id)
            if player:
                player.is_alive = False
                self.db.add(player)
                killed_details.append(
                    {"player_id": player.id, "nickname": player.nickname}
                )
                logger.info(f"Player {player_id} ({player.nickname}) was killed during the night")

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
            # Результаты расследований отправляем лично комиссару ниже
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

        # Check if the game is over (e.g., all mafia dead or mafia outnumber civilians)
        await self.check_game_over()

    async def handle_day(self) -> None:
        """Handle the day phase: discussion and preparation for voting."""
        logger.info(f"Starting day phase for room {self.room_id}, day {self.day_number}")

        # ── Рассылаем итоги ночи всем игрокам ────────────────────────────────
        await self._broadcast(
            {
                "type": "day_started",
                "phase": GamePhase.DAY.value,
                "day_number": self.night_summary.get("day_number", self.day_number),
                "night_results": {
                    "killed": self.night_summary.get("killed", []),
                    "healed": self.night_summary.get("healed", []),
                },
                "message": (
                    "Наступил день. Обсудите произошедшее и проголосуйте за подозреваемого."
                ),
            }
        )

        # In a real game, players discuss and then vote.
        # We'll just wait for a bit and then transition to voting.
        await asyncio.sleep(5)  # Simulate discussion time

        # ── Уведомить о начале фазы голосования ──────────────────────────────
        await self._broadcast(
            {
                "type": "voting_started",
                "phase": GamePhase.VOTING.value,
                "day_number": self.day_number,
                "message": "Время голосовать! Выберите игрока для исключения.",
            }
        )

        # Transition to voting phase
        self.current_phase = GamePhase.VOTING
        await self.update_game_status(GameStatus.VOTING)

    async def handle_voting(self):
        """Handle the voting phase: players vote to eliminate a player."""
        logger.info(f"Starting voting phase for room {self.room_id}, day {self.day_number}")
        # Get alive players
        result = await self.db.execute(
            select(Player).where(Player.room_id == self.room_id, Player.is_alive == True)
        )
        alive_players = result.scalars().all()

        # Reset votes
        self.votes = {}

        # For simplicity, each alive player votes for a random other alive player
        for player in alive_players:
            possible_targets = [p for p in alive_players if p.id != player.id]
            if possible_targets:
                target = random.choice(possible_targets)
                self.votes[player.id] = target.id

        # Count votes
        vote_counts: Dict[int, int] = {}
        for voter_id, target_id in self.votes.items():
            vote_counts[target_id] = vote_counts.get(target_id, 0) + 1

        # Find the player with the most votes
        if vote_counts:
            target_id = max(vote_counts, key=vote_counts.get)
            max_votes = vote_counts[target_id]
            # Check for tie: if multiple players have the same max votes, no one is eliminated
            if list(vote_counts.values()).count(max_votes) > 1:
                logger.info("Vote resulted in a tie, no elimination")
                eliminated_id = None
            else:
                eliminated_id = target_id
                logger.info(f"Player {eliminated_id} received {max_votes} votes and is eliminated")
        else:
            eliminated_id = None

        # Eliminate the player if there is a clear winner
        if eliminated_id is not None:
            player = await self.db.get(Player, eliminated_id)
            if player:
                player.is_alive = False
                self.db.add(player)
                logger.info(f"Player {eliminated_id} ({player.nickname}) was eliminated during voting")

        await self.db.commit()

        # After voting, increment day and check for game over
        self.day_number += 1
        await self.check_game_over()

        # If game not over, transition to night
        if self.current_phase != GamePhase.FINISHED:
            self.current_phase = GamePhase.NIGHT
            await self.update_game_status(GameStatus.NIGHT)

    async def check_game_over(self) -> None:
        """Check if the game is over and set the phase to finished if so."""
        # Get alive players
        result = await self.db.execute(
            select(Player).where(Player.room_id == self.room_id, Player.is_alive == True)
        )
        alive_players = result.scalars().all()
        alive_mafia: List[Player] = [p for p in alive_players if p.role == PlayerRole.MAFIA]
        alive_civilians: List[Player] = [p for p in alive_players if p.role != PlayerRole.MAFIA]

        # Game over conditions:
        # 1. All mafia are dead -> civilians win
        # 2. Mafia number >= civilian number -> mafia wins (since they can control the vote)
        winner: Optional[str]
        if not alive_mafia:
            logger.info(f"Game over: all mafia are dead. Civilians win in room {self.room_id}")
            winner = "civilians"
        elif len(alive_mafia) >= len(alive_civilians):
            logger.info(f"Game over: mafia outnumber or equal civilians. Mafia wins in room {self.room_id}")
            winner = "mafia"
        else:
            # Game continues
            return

        # Set game as finished
        self.current_phase = GamePhase.FINISHED
        await self.update_game_status(GameStatus.FINISHED)

        # Update the game record with the winner
        if self.game_id:
            game: Optional[Game] = await self.db.get(Game, self.game_id)
            if game:
                game.winner = winner
                self.db.add(game)
                await self.db.commit()

        logger.info(f"Game finished in room {self.room_id}. Winner: {winner}")

        # ── Уведомить всех игроков о завершении игры ─────────────────────────
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

    async def update_game_status(self, status: GameStatus):
        """Update the game status in the database."""
        if self.game_id:
            game = await self.db.get(Game, self.game_id)
            if game:
                game.status = status
                self.db.add(game)
                await self.db.commit()
        # Also update the room status if needed (e.g., lobby -> playing)
        room = await self.db.get(Room, self.room_id)
        if room and status in [GameStatus.NIGHT, GameStatus.DAY, GameStatus.VOTING]:
            if room.status == "lobby":
                room.status = "playing"
                self.db.add(room)
                await self.db.commit()