"""
Модели базы данных для AI Mafia Backend.
Этот модуль обеспечивает импорт всех моделей для их регистрации в метаданных SQLAlchemy.
"""

from .base import Base
from .room import Room
from .player import Player
from .game import Game
from .game_event import GameEvent

__all__ = ["Base", "Room", "Player", "Game", "GameEvent"]