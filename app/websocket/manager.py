from typing import Dict, List, Optional, Set
from fastapi import WebSocket
import json
import logging
from app.models.room import Room
from app.models.player import Player
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # room_id -> set of websockets
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        # websocket -> player_id mapping for quick lookup
        self.websocket_player: Dict[WebSocket, int] = {}
        # websocket -> room_id mapping
        self.websocket_room: Dict[WebSocket, int] = {}
        # Ghost chat connections: room_id -> {player_id: WebSocket}
        self.ghost_connections: Dict[int, Dict[int, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: int, player_id: int):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = set()
        self.active_connections[room_id].add(websocket)
        self.websocket_player[websocket] = player_id
        self.websocket_room[websocket] = room_id
        logger.info(f"WebSocket connected for player {player_id} in room {room_id}")

    def disconnect(self, websocket: WebSocket):
        room_id = self.websocket_room.get(websocket)
        player_id = self.websocket_player.get(websocket)
        if room_id and room_id in self.active_connections:
            self.active_connections[room_id].discard(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]
        if websocket in self.websocket_player:
            del self.websocket_player[websocket]
        if websocket in self.websocket_room:
            del self.websocket_room[websocket]
        logger.info(f"WebSocket disconnected for player {player_id} in room {room_id}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)

    async def broadcast_to_room(self, room_id: int, message: dict) -> None:
        if room_id in self.active_connections:
            disconnected: Set[WebSocket] = set()
            for websocket in self.active_connections[room_id]:
                try:
                    await websocket.send_text(json.dumps(message))
                except Exception as e:
                    logger.error(f"Error broadcasting to websocket: {e}")
                    disconnected.add(websocket)
            # Remove disconnected websockets
            for websocket in disconnected:
                self.disconnect(websocket)

    async def send_to_player(self, player_id: int, message: dict) -> None:
        """Send a message to a specific connected player by player_id."""
        for websocket, pid in list(self.websocket_player.items()):
            if pid == player_id:
                try:
                    await websocket.send_text(json.dumps(message))
                except Exception as e:
                    logger.error(f"Error sending message to player {player_id}: {e}")
                    self.disconnect(websocket)
                return  # player_id is unique, stop after first match

    async def disconnect_player(self, player_id: int) -> bool:
        """Force-disconnect a specific player by player_id. Returns True if found."""
        for websocket, pid in list(self.websocket_player.items()):
            if pid == player_id:
                try:
                    await websocket.close()
                except Exception:
                    pass
                self.disconnect(websocket)
                return True
        return False

    async def broadcast_to_players(self, player_ids: List[int], message: dict) -> None:
        """Broadcast a message only to specific players by their IDs."""
        player_id_set: Set[int] = set(player_ids)
        disconnected: Set[WebSocket] = set()
        for websocket, pid in list(self.websocket_player.items()):
            if pid in player_id_set:
                try:
                    await websocket.send_text(json.dumps(message))
                except Exception as e:
                    logger.error(f"Error broadcasting to player {pid}: {e}")
                    disconnected.add(websocket)
        for websocket in disconnected:
            self.disconnect(websocket)

    async def connect_ghost(
        self, websocket: WebSocket, room_id: int, player_id: int
    ) -> None:
        """Подключить мёртвого игрока или зрителя к Ghost Chat (новое соединение)."""
        await websocket.accept()
        if room_id not in self.ghost_connections:
            self.ghost_connections[room_id] = {}
        self.ghost_connections[room_id][player_id] = websocket
        logger.info(f"Ghost connected: player {player_id} in room {room_id}")

    def disconnect_ghost(self, room_id: int, player_id: int) -> None:
        """Отключить игрока от Ghost Chat."""
        if room_id in self.ghost_connections:
            self.ghost_connections[room_id].pop(player_id, None)
            if not self.ghost_connections[room_id]:
                del self.ghost_connections[room_id]
        logger.info(f"Ghost disconnected: player {player_id} in room {room_id}")

    async def broadcast_to_ghosts(self, room_id: int, message: dict) -> None:
        """Разослать сообщение всем призракам и зрителям в комнате."""
        if room_id not in self.ghost_connections:
            return

        disconnected: List[int] = []
        for player_id, ws in list(self.ghost_connections[room_id].items()):
            try:
                await ws.send_text(json.dumps(message))
            except Exception as e:
                logger.error(
                    f"Error sending ghost message to player {player_id}: {e}"
                )
                disconnected.append(player_id)

        for pid in disconnected:
            self.disconnect_ghost(room_id, pid)

    async def move_to_ghost(self, room_id: int, player_id: int) -> None:
        """
        Перевести живого игрока в Ghost Chat после смерти.

        Ищет активное WebSocket-соединение игрока, уведомляет его о смерти
        и переносит сокет в ghost_connections; из active_connections удаляет.
        """
        # Находим WebSocket игрока
        target_ws: Optional[WebSocket] = None
        for ws, pid in list(self.websocket_player.items()):
            if pid == player_id:
                target_ws = ws
                break

        if target_ws is None:
            logger.debug(
                f"move_to_ghost: no active WS for player {player_id} in room {room_id}"
            )
            return

        # Уведомляем игрока о смерти
        try:
            await target_ws.send_text(
                json.dumps(
                    {
                        "event": "you_died",
                        "data": {
                            "message": (
                                "You have died. You can now chat "
                                "with other dead players."
                            ),
                            "ghost_chat_enabled": True,
                        },
                    }
                )
            )
        except Exception:
            pass

        # Убираем из active_connections
        if room_id in self.active_connections:
            self.active_connections[room_id].discard(target_ws)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]

        # Добавляем в ghost_connections (сохраняем маппинги ws_player/ws_room)
        if room_id not in self.ghost_connections:
            self.ghost_connections[room_id] = {}
        self.ghost_connections[room_id][player_id] = target_ws

        logger.info(
            f"Player {player_id} moved to ghost chat in room {room_id}"
        )

    async def get_player_info(self, websocket: WebSocket, db: AsyncSession) -> dict:
        player_id = self.websocket_player.get(websocket)
        room_id = self.websocket_room.get(websocket)
        if player_id is None or room_id is None:
            return {}
        # Fetch player and room details from DB
        from app.crud import player as player_crud, room as room_crud
        player = await player_crud.get(db, id=player_id)
        room = await room_crud.get(db, id=room_id)
        if not player or not room:
            return {}
        return {
            "player_id": player.id,
            "player_uuid": player.player_id,
            "nickname": player.nickname,
            "is_ai": player.is_ai,
            "role": player.role,
            "is_alive": player.is_alive,
            "room_id": room.id,
            "room_uuid": room.room_id,
            "room_status": room.status,
        }


# Global manager instance
manager = ConnectionManager()