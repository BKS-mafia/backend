"""
Сервисный слой приложения AI Mafia.
"""

from .room_service import RoomService, room_service
from .game_service import GameService, game_service
from .ai_service import AIService, AICharacter, ai_service

__all__ = [
    # Классы
    "RoomService",
    "GameService",
    "AIService",
    "AICharacter",
    # Глобальные экземпляры
    "room_service",
    "game_service",
    "ai_service",
]