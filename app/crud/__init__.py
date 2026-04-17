"""
CRUD операции для работы с моделями базы данных.
Содержит модули для Room, Player, Game и GameEvent.
"""
from .room import RoomCRUD
from .player import PlayerCRUD

# Глобальные экземпляры для удобного импорта
room = RoomCRUD()
player = PlayerCRUD()

__all__ = ["room", "player", "RoomCRUD", "PlayerCRUD"]