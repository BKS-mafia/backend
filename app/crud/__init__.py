"""
CRUD операции для работы с моделями базы данных.
Содержит модули для Room, Player, Game и GameEvent.
"""
from .room import RoomCRUD
from .player import PlayerCRUD
from .game import GameCRUD

# Глобальные экземпляры для удобного импорта
room = RoomCRUD()
player = PlayerCRUD()
game = GameCRUD()

__all__ = ["room", "player", "game", "RoomCRUD", "PlayerCRUD", "GameCRUD"]