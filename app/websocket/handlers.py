from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.websocket.manager import manager
from app.db.session import get_db
from app import crud, schemas
from app.models.player import Player as PlayerModel, PlayerRole
from app.models.game_event import GameEvent
from app.game.state_machine import GamePhase
from app.services.game_service import game_service
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/rooms/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket endpoint for room communication.
    Authenticates the player via session token and handles the message loop.
    """
    # Verify the token and get player info
    player: Optional[PlayerModel] = await crud.player.get_by_session_token(
        db, session_token=token
    )
    if not player:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Verify the player is in the specified room (room_id is public UUID, player.room_id is int FK)
    room = await crud.room.get_by_room_id(db, room_id=room_id)
    if not room or room.id != player.room_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Connect to the manager
    await manager.connect(websocket, player.room_id, player.id)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                await handle_websocket_message(websocket, player, message, db)
            except json.JSONDecodeError:
                await manager.send_personal_message(
                    {"error": "Invalid JSON format"}, websocket
                )
    except WebSocketDisconnect:
        await _handle_disconnect(websocket, player, db)
    except Exception as e:
        logger.error(f"WebSocket error for player {player.id}: {e}")
        await _handle_disconnect(websocket, player, db)


async def _handle_disconnect(
    websocket: WebSocket,
    player: PlayerModel,
    db: AsyncSession,
) -> None:
    """
    Handle player disconnect.
    If a game is running, marks the player as disconnected (is_connected=False)
    without deleting the record from the database.
    Broadcasts player_disconnected event to remaining room members.
    """
    room_id = player.room_id

    # Disconnect from manager first (removes this WS, remaining can still receive)
    manager.disconnect(websocket)

    # Broadcast disconnect notification to room
    await manager.broadcast_to_room(
        room_id,
        {
            "type": "player_disconnected",
            "player_id": player.id,
            "nickname": player.nickname,
        },
    )

    # Check if game is active for this player's room
    machine = game_service.active_machines.get(room_id)
    if machine is not None:
        # Game is in progress — mark player as disconnected, keep in DB
        try:
            await crud.player.update(
                db,
                db_obj=player,
                obj_in=schemas.PlayerUpdate(is_connected=False),
            )
            logger.info(
                f"Player {player.id} ({player.nickname!r}) marked as disconnected "
                f"during active game in room {room_id}"
            )
        except Exception as exc:
            logger.error(
                f"Failed to mark player {player.id} as disconnected: {exc}"
            )
    else:
        logger.info(
            f"Player {player.id} ({player.nickname!r}) disconnected "
            f"(no active game in room {room_id})"
        )


async def handle_websocket_message(
    websocket: WebSocket,
    player: PlayerModel,
    message: Dict[str, Any],
    db: AsyncSession,
) -> None:
    """
    Route an incoming WebSocket message to the appropriate handler
    based on the 'type' field.
    """
    event_type: Optional[str] = message.get("type")

    if event_type == "chat_message":
        await handle_chat_message(websocket, player, message, db)
    elif event_type == "ghost_chat":
        if not player.is_alive:
            await handle_ghost_chat_message(websocket, player, message, db)
        else:
            await manager.send_personal_message(
                {"event": "error", "data": {"message": "You are still alive!"}},
                websocket,
            )
    elif event_type == "vote_action":
        await handle_vote_action(websocket, player, message, db)
    elif event_type == "start_game":
        await handle_start_game(websocket, player, message, db)
    elif event_type == "night_action":
        await handle_night_action(websocket, player, message, db)
    elif event_type == "ready":
        await handle_ready(websocket, player, message, db)
    elif event_type == "reconnect":
        await handle_reconnect(websocket, player, message, db)
    elif event_type == "kick_player":
        await handle_kick_player(websocket, player, message, db)
    elif event_type == "turing_test_vote":
        # Получаем state_machine из game_service
        state_machine = game_service.active_machines.get(player.room_id)
        await handle_turing_test_vote(
            websocket=websocket,
            room_id=player.room_id,
            player_id=player.id,
            data=message,
            db=db,
            ws_manager=manager,
            state_machine=state_machine
        )
    else:
        await manager.send_personal_message(
            {"error": f"Unknown event type: {event_type!r}"}, websocket
        )


async def handle_start_game(
    websocket: WebSocket,
    player: PlayerModel,
    message: Dict[str, Any],
    db: AsyncSession,
) -> None:
    """
    Handle the 'start_game' command from the room host.

    1. Verifies the requesting player is the room host.
    2. Checks minimum player count.
    3. Delegates to game_service.start_game_for_room, which:
       - Creates the Game record in the DB
       - Launches the StateMachine
       - Broadcasts 'game_started' to all players in the room
    """
    room = await crud.room.get(db, id=player.room_id)
    if not room or room.host_token != player.session_token:
        await manager.send_personal_message(
            {"error": "Only the host can start the game"}, websocket
        )
        return

    if room.current_players < room.min_players:
        await manager.send_personal_message(
            {
                "error": (
                    f"Not enough players to start the game. "
                    f"Minimum required: {room.min_players}, "
                    f"currently in room: {room.current_players}"
                )
            },
            websocket,
        )
        return

    try:
        await game_service.start_game_for_room(db, room.id)
        logger.info(
            f"Game started for room {room.id} by player {player.id} ({player.nickname!r})"
        )
    except ValueError as exc:
        await manager.send_personal_message({"error": str(exc)}, websocket)


async def handle_chat_message(
    websocket: WebSocket,
    player: PlayerModel,
    message: Dict[str, Any],
    db: AsyncSession,
) -> None:
    """
    Handle a 'chat_message' event.

    - During the NIGHT phase: only Mafia players may chat, and their messages
      are delivered exclusively to other Mafia members (private channel).
    - During any other phase (or when no game is active): the message is
      broadcast to all players in the room.

    Chat messages are persisted as GameEvent records when an active game exists.
    """
    content: str = message.get("content", "").strip()
    if not content:
        await manager.send_personal_message(
            {"error": "Message content cannot be empty"}, websocket
        )
        return

    # Мёртвые игроки не могут писать в основной чат — перенаправляем в Ghost Chat
    if not player.is_alive:
        await handle_ghost_chat_message(websocket, player, message, db)
        return

    # Retrieve the active game for this room (may be None before game starts)
    game = await crud.game.get_by_room(db, room_id=player.room_id)

    # Determine the current game phase from the running StateMachine
    machine = game_service.active_machines.get(player.room_id)
    current_phase: Optional[GamePhase] = machine.current_phase if machine else None

    # ── Night phase: Mafia-only channel ──────────────────────────────────────
    if current_phase == GamePhase.NIGHT:
        if player.role != PlayerRole.MAFIA:
            await manager.send_personal_message(
                {"error": "Chat is disabled for non-Mafia players during the night phase"},
                websocket,
            )
            return

        # Collect IDs of all alive Mafia players in this room
        all_room_players: List[PlayerModel] = await crud.player.get_by_room(
            db, room_id=player.room_id
        )
        mafia_player_ids: List[int] = [
            p.id
            for p in all_room_players
            if p.role == PlayerRole.MAFIA and p.is_alive
        ]

        mafia_payload: Dict[str, Any] = {
            "type": "chat_event",
            "player_id": player.id,
            "nickname": player.nickname,
            "content": content,
            "is_ai": player.is_ai,
            "is_mafia_channel": True,
        }

        # Persist as a game event if a game record exists
        if game:
            db.add(
                GameEvent(
                    game_id=game.id,
                    player_id=player.id,
                    event_type="chat_mafia",
                    event_data=json.dumps(
                        {"content": content, "nickname": player.nickname}
                    ),
                )
            )
            await db.commit()

        await manager.broadcast_to_players(mafia_player_ids, mafia_payload)
        return

    # ── Default: broadcast to all players in the room ────────────────────────
    chat_payload: Dict[str, Any] = {
        "type": "chat_event",
        "player_id": player.id,
        "nickname": player.nickname,
        "content": content,
        "is_ai": player.is_ai,
        "is_mafia_channel": False,
    }

    if game:
        db.add(
            GameEvent(
                game_id=game.id,
                player_id=player.id,
                event_type="chat",
                event_data=json.dumps(
                    {"content": content, "nickname": player.nickname}
                ),
            )
        )
        await db.commit()

    await manager.broadcast_to_room(player.room_id, chat_payload)


async def handle_ghost_chat_message(
    websocket: WebSocket,
    player: PlayerModel,
    message: Dict[str, Any],
    db: AsyncSession,
) -> None:
    """
    Обработка сообщения от мёртвых игроков (Ghost Chat).

    Сообщение видят только мёртвые + зрители — рассылается через
    manager.broadcast_to_ghosts(). Живые игроки это сообщение не получают.
    """
    if player.is_alive:
        # Живые не имеют доступа к Ghost Chat
        await manager.send_personal_message(
            {"event": "error", "data": {"message": "You are still alive!"}},
            websocket,
        )
        return

    content: str = message.get("content", "").strip()
    if not content:
        await manager.send_personal_message(
            {"error": "Ghost message content cannot be empty"}, websocket
        )
        return

    ghost_message: Dict[str, Any] = {
        "event": "ghost_chat_message",
        "data": {
            "sender_id": player.id,
            "sender_name": player.nickname or f"Ghost_{player.id}",
            "content": content,
            "is_ghost": True,
        },
    }

    # Рассылаем только призракам и зрителям
    await manager.broadcast_to_ghosts(player.room_id, ghost_message)
    logger.info(
        f"Ghost message from player {player.id} ({player.nickname!r}) "
        f"in room {player.room_id}: {content!r}"
    )


async def handle_vote_action(
    websocket: WebSocket,
    player: PlayerModel,
    message: Dict[str, Any],
    db: AsyncSession,
) -> None:
    """
    Handle a 'vote_action' event.

    The behaviour depends on the current game phase:

    - GamePhase.VOTING (day voting):
        Calls game_service.submit_vote(voter_id, target_player_id).
        Broadcasts vote_received to all players (handled inside the service).

    - GamePhase.NIGHT (night action):
        Requires an 'action_type' field in the message: 'kill', 'heal', or
        'investigate'.  Calls game_service.submit_night_action with the
        structured action dict.

    - Any other phase: returns an error message.

    Expected message payload:
        {
            "type": "vote_action",
            "target_player_id": <int>,
            "action_type": "kill" | "heal" | "investigate"   // required for night
        }
    """
    target_player_id: Optional[int] = message.get("target_player_id")
    if not target_player_id:
        await manager.send_personal_message(
            {"error": "target_player_id is required"}, websocket
        )
        return

    # Retrieve the running StateMachine for the room
    machine = game_service.active_machines.get(player.room_id)
    if not machine:
        await manager.send_personal_message(
            {"error": "No active game found in this room"}, websocket
        )
        return

    current_phase: GamePhase = machine.current_phase

    try:
        # ── Day voting phase ──────────────────────────────────────────────────
        if current_phase == GamePhase.VOTING:
            await game_service.submit_vote(
                db=db,
                room_id=player.room_id,
                voter_id=player.id,
                target_player_id=target_player_id,
            )
            # Personal acknowledgement; broadcast was already done inside
            # submit_vote via ws_manager.broadcast_to_room
            await manager.send_personal_message(
                {
                    "type": "vote_accepted",
                    "voter_id": player.id,
                    "target_player_id": target_player_id,
                },
                websocket,
            )

        # ── Night action phase ────────────────────────────────────────────────
        elif current_phase == GamePhase.NIGHT:
            action_type: str = message.get("action_type", "")
            valid_action_types = ("kill", "heal", "investigate")
            if action_type not in valid_action_types:
                await manager.send_personal_message(
                    {
                        "error": (
                            "action_type is required for the night phase and must be "
                            "one of: kill, heal, investigate"
                        )
                    },
                    websocket,
                )
                return

            await game_service.submit_night_action(
                db=db,
                room_id=player.room_id,
                player_id=player.id,
                action={"action": action_type, "target_id": target_player_id},
            )
            # Personal acknowledgement is sent by submit_night_action via
            # ws_manager.send_to_player; we also confirm here for reliability
            await manager.send_personal_message(
                {
                    "type": "night_action_accepted",
                    "player_id": player.id,
                    "action_type": action_type,
                    "target_player_id": target_player_id,
                },
                websocket,
            )

        # ── Wrong phase ───────────────────────────────────────────────────────
        else:
            await manager.send_personal_message(
                {
                    "error": (
                        f"Voting and night actions are not available "
                        f"during the '{current_phase.value}' phase"
                    )
                },
                websocket,
            )

    except ValueError as exc:
        await manager.send_personal_message({"error": str(exc)}, websocket)


async def handle_night_action(
    websocket: WebSocket,
    player: PlayerModel,
    message: Dict[str, Any],
    db: AsyncSession,
) -> None:
    """
    Handle a 'night_action' event from a player during the night phase.

    Expected payload:
        {
            "type": "night_action",
            "action_type": "kill" | "heal" | "check",
            "target_player_id": <int>
        }

    Role restrictions:
        - MAFIA: "kill"
        - DOCTOR: "heal"
        - COMMISSIONER: "check"
    """
    machine = game_service.active_machines.get(player.room_id)
    if not machine:
        await manager.send_personal_message(
            {"error": "No active game found in this room"}, websocket
        )
        return

    if machine.current_phase != GamePhase.NIGHT:
        await manager.send_personal_message(
            {"error": "Night actions are only available during the night phase"}, websocket
        )
        return

    action_type: str = message.get("action_type", "")
    target_player_id: Optional[int] = message.get("target_player_id")

    valid_action_types = ("kill", "heal", "check")
    if action_type not in valid_action_types:
        await manager.send_personal_message(
            {"error": f"action_type must be one of: {', '.join(valid_action_types)}"}, websocket
        )
        return

    if not target_player_id:
        await manager.send_personal_message(
            {"error": "target_player_id is required"}, websocket
        )
        return

    # Verify that the player is alive
    if not player.is_alive:
        await manager.send_personal_message(
            {"error": "Dead players cannot perform actions"}, websocket
        )
        return

    try:
        await game_service.submit_night_action(
            db=db,
            room_id=player.room_id,
            player_id=player.id,
            action={"action": action_type, "target_id": target_player_id},
        )
        await manager.send_personal_message(
            {
                "type": "night_action_accepted",
                "player_id": player.id,
                "action_type": action_type,
                "target_player_id": target_player_id,
            },
            websocket,
        )
        logger.info(
            f"Night action from player {player.id} ({player.nickname!r}): "
            f"{action_type} -> target {target_player_id}"
        )
    except ValueError as exc:
        await manager.send_personal_message({"error": str(exc)}, websocket)


async def handle_ready(
    websocket: WebSocket,
    player: PlayerModel,
    message: Dict[str, Any],
    db: AsyncSession,
) -> None:
    """
    Handle a 'ready' event — player indicates they are ready to start.

    Expected payload:
        {"type": "ready"}

    When all players in the room mark themselves as ready,
    the host receives a 'all_players_ready' notification.
    """
    room_id = player.room_id

    # Track ready players per room
    if room_id not in game_service.ready_players:
        game_service.ready_players[room_id] = set()
    game_service.ready_players[room_id].add(player.id)

    await manager.send_personal_message(
        {"type": "ready_acknowledged", "player_id": player.id}, websocket
    )

    # Broadcast to all that this player is ready
    await manager.broadcast_to_room(
        room_id,
        {
            "type": "player_ready",
            "player_id": player.id,
            "nickname": player.nickname,
        },
    )

    # Check if all human (connected) players are ready
    all_players: List[PlayerModel] = await crud.player.get_by_room(db, room_id=room_id)
    human_players = [p for p in all_players if not p.is_ai and p.is_connected]
    ready_count = len(game_service.ready_players[room_id])
    total_count = len(human_players)

    if total_count > 0 and ready_count >= total_count:
        # Notify the host that everyone is ready
        room = await crud.room.get(db, id=room_id)
        if room:
            await manager.broadcast_to_room(
                room_id,
                {
                    "type": "all_players_ready",
                    "room_id": room_id,
                    "ready_count": ready_count,
                    "total_count": total_count,
                },
            )
        logger.info(f"All {ready_count} players ready in room {room_id}")


async def handle_reconnect(
    websocket: WebSocket,
    player: PlayerModel,
    message: Dict[str, Any],
    db: AsyncSession,
) -> None:
    """
    Handle a 'reconnect' event — player requests current game state after reconnecting.

    Expected payload:
        {"type": "reconnect", "session_token": "<uuid>"}

    Verifies the token and sends back the current game state.
    """
    session_token: Optional[str] = message.get("session_token")

    # If token is provided, verify it matches the authenticated player
    if session_token and session_token != player.session_token:
        await manager.send_personal_message(
            {"error": "Invalid session token"}, websocket
        )
        return

    # Mark player as connected again
    try:
        await crud.player.update(
            db,
            db_obj=player,
            obj_in=schemas.PlayerUpdate(is_connected=True),
        )
    except Exception as exc:
        logger.error(f"Failed to mark player {player.id} as connected: {exc}")

    room_id = player.room_id
    machine = game_service.active_machines.get(room_id)

    # Build current state payload
    all_players: List[PlayerModel] = await crud.player.get_by_room(db, room_id=room_id)
    game = await crud.game.get_by_room(db, room_id=room_id)

    state_payload: Dict[str, Any] = {
        "type": "reconnect_state",
        "player_id": player.id,
        "nickname": player.nickname,
        "role": player.role.value if player.role else None,
        "is_alive": player.is_alive,
        "room_id": room_id,
        "game_id": game.id if game else None,
        "game_status": game.status if game else None,
        "phase": machine.current_phase.value if machine and machine.current_phase else None,
        "day_number": machine.day_number if machine else None,
        "players": [
            {
                "id": p.id,
                "nickname": p.nickname,
                "is_alive": p.is_alive,
                "is_ai": p.is_ai,
                "is_connected": p.is_connected,
            }
            for p in all_players
        ],
    }

    await manager.send_personal_message(state_payload, websocket)

    # Notify room that this player reconnected
    await manager.broadcast_to_room(
        room_id,
        {
            "type": "player_reconnected",
            "player_id": player.id,
            "nickname": player.nickname,
        },
    )
    logger.info(f"Player {player.id} ({player.nickname!r}) reconnected to room {room_id}")


async def handle_kick_player(
    websocket: WebSocket,
    player: PlayerModel,
    message: Dict[str, Any],
    db: AsyncSession,
) -> None:
    """
    Handle a 'kick_player' event — host removes a player from the room.

    Expected payload:
        {"type": "kick_player", "player_id": <int>}

    Only the room host (session_token == room.host_token) can kick players.
    """
    target_player_id: Optional[int] = message.get("player_id")
    if not target_player_id:
        await manager.send_personal_message(
            {"error": "player_id is required"}, websocket
        )
        return

    # Load room and verify host
    room = await crud.room.get(db, id=player.room_id)
    if not room or room.host_token != player.session_token:
        await manager.send_personal_message(
            {"error": "Only the host can kick players"}, websocket
        )
        return

    # Cannot kick yourself
    if target_player_id == player.id:
        await manager.send_personal_message(
            {"error": "Host cannot kick themselves"}, websocket
        )
        return

    # Load target player
    target_player = await crud.player.get(db, id=target_player_id)
    if not target_player or target_player.room_id != player.room_id:
        await manager.send_personal_message(
            {"error": "Player not found in this room"}, websocket
        )
        return

    target_nickname = target_player.nickname

    # Notify target player before disconnecting
    await manager.send_to_player(
        target_player_id,
        {
            "type": "kicked",
            "message": "You have been kicked from the room by the host.",
        },
    )

    # Force-disconnect the player's WebSocket
    await manager.disconnect_player(target_player_id)

    # Remove the player from DB
    try:
        await crud.player.delete(db, id=target_player_id)

        # Update room player count
        new_count = max(0, room.current_players - 1)
        human_delta = 0 if target_player.is_ai else 1
        ai_delta = 1 if target_player.is_ai else 0
        await crud.room.update(
            db,
            db_obj=room,
            obj_in=schemas.RoomUpdate(
                current_players=new_count,
                human_players=max(0, room.human_players - human_delta),
                ai_players=max(0, room.ai_players - ai_delta),
            ),
        )
    except Exception as exc:
        logger.error(f"Failed to remove kicked player {target_player_id} from DB: {exc}")

    # Notify everyone remaining
    await manager.broadcast_to_room(
        player.room_id,
        {
            "type": "player_kicked",
            "player_id": target_player_id,
            "nickname": target_nickname,
            "kicked_by": player.nickname,
        },
    )
    logger.info(
        f"Player {target_player_id} ({target_nickname!r}) kicked from room "
        f"{player.room_id} by host {player.id} ({player.nickname!r})"
    )


async def handle_turing_test_vote(
    websocket: WebSocket,
    room_id: int,
    player_id: int,
    data: dict,
    db: AsyncSession,
    ws_manager,
    state_machine=None
) -> None:
    """
    Обработать голос в Тесте Тьюринга.
    
    Ожидаемые данные:
    {
        "type": "turing_test_vote",
        "suspected_ai_ids": [1, 3, 5]  // список ID игроков которых считаем ИИ
    }
    """
    suspected_ai_ids = data.get("suspected_ai_ids", [])
    
    if not isinstance(suspected_ai_ids, list):
        await ws_manager.send_personal_message(
            {"event": "error", "data": {"message": "suspected_ai_ids must be a list of player IDs"}},
            websocket
        )
        return
    
    # Фильтруем валидные ID (не сам игрок)
    valid_ids = [pid for pid in suspected_ai_ids if isinstance(pid, int) and pid != player_id]
    
    if state_machine and state_machine.current_phase == GamePhase.TURING_TEST:
        await state_machine._handle_turing_test_vote(
            voter_id=player_id,
            suspected_ai_ids=valid_ids
        )
    else:
        await ws_manager.send_personal_message(
            {"event": "error", "data": {"message": "Game not found or not in Turing Test phase"}},
            websocket
        )
