"""
CRUD операции для работы с моделями базы данных.
Содержит модули для Room, Player, Game и GameEvent.
"""
from .room import RoomCRUD
from .player import PlayerCRUD
from .game import GameCRUD
from .game_event import GameEventCRUD

# Глобальные экземпляры для удобного импорта
room = RoomCRUD()
player = PlayerCRUD()
game = GameCRUD()
game_event = GameEventCRUD()

__all__ = [
    "room", "player", "game", "game_event",
    "RoomCRUD", "PlayerCRUD", "GameCRUD", "GameEventCRUD",
]
