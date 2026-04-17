"""
AI Mafia Backend – асинхронный бэкенд для игры "Мафия" с ИИ.
"""

__version__ = "0.1.0"
__author__ = "AI Mafia Team"

# Экспорт основных объектов для удобного импорта
from app.core.config import settings
from app.db.session import get_db, init_db, close_db
from app.redis.client import get_redis, close_redis
from app import crud, schemas

__all__ = [
    "settings",
    "get_db",
    "init_db",
    "close_db",
    "get_redis",
    "close_redis",
    "crud",
    "schemas",
]