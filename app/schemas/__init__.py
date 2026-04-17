"""
Pydantic схемы для валидации данных.
Экспортирует все модели для удобного импорта.
"""
from .room import (
    RoomBase,
    RoomCreate,
    RoomUpdate,
    RoomInDBBase,
    Room,
)
from .player import (
    PlayerBase,
    PlayerCreate,
    PlayerUpdate,
    PlayerInDBBase,
    Player,
)
from .game import (
    GameBase,
    GameCreate,
    GameUpdate,
    GameInDBBase,
    Game,
)
from .game_event import (
    GameEventBase,
    GameEventCreate,
    GameEventUpdate,
    GameEventInDBBase,
    GameEvent,
)

__all__ = [
    # Room schemas
    "RoomBase",
    "RoomCreate",
    "RoomUpdate",
    "RoomInDBBase",
    "Room",
    # Player schemas
    "PlayerBase",
    "PlayerCreate",
    "PlayerUpdate",
    "PlayerInDBBase",
    "Player",
    # Game schemas
    "GameBase",
    "GameCreate",
    "GameUpdate",
    "GameInDBBase",
    "Game",
    # GameEvent schemas
    "GameEventBase",
    "GameEventCreate",
    "GameEventUpdate",
    "GameEventInDBBase",
    "GameEvent",
]