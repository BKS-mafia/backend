"""
Утилиты для генерации коротких ID.
"""
import random
import string
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.room import Room as RoomModel


def generate_short_id(length: int = 5) -> str:
    """
    Генерирует случайную строку из букв и цифр (A-Z, a-z, 0-9).
    
    Args:
        length: Длина генерируемой строки (по умолчанию 5)
    
    Returns:
        Случайная строка указанной длины
    """
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


async def generate_unique_short_id(db: AsyncSession, length: int = 5, max_attempts: int = 10) -> str:
    """
    Генерирует уникальный short_id, которого нет в базе данных.
    
    Args:
        db: Сессия базы данных
        length: Длина генерируемой строки (по умолчанию 5)
        max_attempts: Максимальное количество попыток генерации
    
    Returns:
        Уникальная строка short_id
    
    Raises:
        ValueError: Если не удалось сгенерировать уникальный ID после max_attempts попыток
    """
    for attempt in range(max_attempts):
        short_id = generate_short_id(length)
        
        # Проверяем, есть ли уже такой short_id в базе
        stmt = select(RoomModel).where(RoomModel.short_id == short_id)
        result = await db.execute(stmt)
        existing_room = result.scalar_one_or_none()
        
        if existing_room is None:
            return short_id
    
    raise ValueError(f"Не удалось сгенерировать уникальный short_id после {max_attempts} попыток")