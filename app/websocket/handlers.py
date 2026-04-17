from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.websocket.manager import manager
from app.db.session import get_db
from app import crud, schemas
import json
import logging
import asyncio
from typing import Dict, Any

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/rooms/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for room communication.
    """
    # Verify the token and get player info
    # For simplicity, we assume token is the session_token of the player
    # In a real app, you would verify the token properly (e.g., JWT)
    player = await crud.player.get_by_session_token(db, session_token=token)
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
                    {"error": "Invalid JSON"}, websocket
                )
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def handle_websocket_message(
    websocket: WebSocket,
    player: schemas.Player,
    message: Dict[str, Any],
    db: AsyncSession
):
    """
    Handle incoming WebSocket messages based on event type.
    """
    event_type = message.get("type")
    if event_type == "chat_message":
        await handle_chat_message(websocket, player, message, db)
    elif event_type == "vote_action":
        await handle_vote_action(websocket, player, message, db)
    elif event_type == "start_game":
        await handle_start_game(websocket, player, message, db)
    else:
        await manager.send_personal_message(
            {"error": f"Unknown event type: {event_type}"}, websocket
        )


async def handle_chat_message(
    websocket: WebSocket,
    player: schemas.Player,
    message: Dict[str, Any],
    db: AsyncSession
):
    """
    Handle a chat message from a player.
    """
    content = message.get("content", "")
    if not content:
        await manager.send_personal_message(
            {"error": "Message content is empty"}, websocket
        )
        return

    # Save the chat message to the database (as a game event)
    # For simplicity, we'll create a game event of type "chat"
    # In a real app, you might have a separate chat table or use Redis for chat history
    from app.models.game_event import GameEvent
    # We need to get the current active game for the room
    # For now, we'll assume there is a game in progress or we create a dummy game event
    # This is a simplification; in a real app, you would manage the game state properly
    game_event = GameEvent(
        game_id=1,  # TODO: Get the current active game ID for the room
        player_id=player.id,
        event_type="chat",
        event_data=json.dumps({"content": content, "nickname": player.nickname})
    )
    db.add(game_event)
    await db.commit()

    # Broadcast the chat message to all players in the room
    await manager.broadcast_to_room(
        player.room_id,
        {
            "type": "chat_event",
            "player_id": player.id,
            "nickname": player.nickname,
            "content": content,
            "is_ai": player.is_ai
        }
    )


async def handle_vote_action(
    websocket: WebSocket,
    player: schemas.Player,
    message: Dict[str, Any],
    db: AsyncSession
):
    """
    Handle a vote action from a player.
    """
    target_player_id = message.get("target_player_id")
    if not target_player_id:
        await manager.send_personal_message(
            {"error": "Target player ID is required"}, websocket
        )
        return

    # Save the vote as a game event
    from app.models.game_event import GameEvent
    game_event = GameEvent(
        game_id=1,  # TODO: Get the current active game ID for the room
        player_id=player.id,
        event_type="vote",
        event_data=json.dumps({"target_player_id": target_player_id})
    )
    db.add(game_event)
    await db.commit()

    # Broadcast the vote to the room (optional, depending on game rules)
    # For example, in Mafia, votes are typically revealed during the voting phase
    await manager.broadcast_to_room(
        player.room_id,
        {
            "type": "vote_action",
            "voter_id": player.id,
            "target_player_id": target_player_id
        }
    )


async def handle_start_game(
    websocket: WebSocket,
    player: schemas.Player,
    message: Dict[str, Any],
    db: AsyncSession
):
    """
    Handle the start game command from the host.
    """
    # Check if the player is the host of the room
    room = await crud.room.get(db, id=player.room_id)
    if not room or room.host_token != player.session_token:
        await manager.send_personal_message(
            {"error": "Only the host can start the game"}, websocket
        )
        return

    # Check if there are enough players to start
    if room.current_players < room.min_players:
        await manager.send_personal_message(
            {"error": f"Not enough players to start. Minimum {room.min_players} required"}, websocket
        )
        return

    # TODO: Implement game start logic (assign roles, set up state machine, etc.)
    # For now, we'll just update the room status and broadcast
    room.status = "starting"
    await db.commit()

    await manager.broadcast_to_room(
        player.room_id,
        {
            "type": "game_state_update",
            "status": room.status
        }
    )

    # TODO: Trigger the actual game start (e.g., assign roles, start timers, etc.)
    # This would involve the State Machine and AI agents