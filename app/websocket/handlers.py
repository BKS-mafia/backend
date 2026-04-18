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

    # Verify the player is in the specified room
    if str(player.room_id) != room_id:
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
    """
    manager.disconnect(websocket)

    # Check if game is active for this player's room
    machine = game_service.active_machines.get(player.room_id)
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
                f"during active game in room {player.room_id}"
            )
        except Exception as exc:
            logger.error(
                f"Failed to mark player {player.id} as disconnected: {exc}"
            )
    else:
        logger.info(
            f"Player {player.id} ({player.nickname!r}) disconnected "
            f"(no active game in room {player.room_id})"
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
    elif event_type == "vote_action":
        await handle_vote_action(websocket, player, message, db)
    elif event_type == "start_game":
        await handle_start_game(websocket, player, message, db)
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
