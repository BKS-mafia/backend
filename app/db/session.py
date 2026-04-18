"""
Асинхронная сессия SQLAlchemy для работы с PostgreSQL.
Создаёт движок, фабрику сессий и dependency injection для FastAPI.
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import settings
from app.models.base import Base

# Асинхронный движок БД
async_engine: AsyncEngine = create_async_engine(
    str(settings.DATABASE_URL),
    echo=settings.SQL_ECHO,
    pool_pre_ping=True,  # проверка соединения перед использованием
    pool_recycle=3600,   # переподключение каждые час
)

# Фабрика асинхронных сессий
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Генератор асинхронных сессий БД для dependency injection в FastAPI.
    
    Использование:
        from app.db.session import get_db
        from fastapi import Depends
        
        async def some_endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # Проверяем, есть ли активная транзакция перед закрытием
            if session.in_transaction():
                await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            # Проверяем состояние перед закрытием
            try:
                # Если есть активная транзакция, откатываем её
                if session.in_transaction():
                    await session.rollback()
                await session.close()
            except Exception as e:
                # Логируем ошибку закрытия, но не поднимаем исключение
                import logging
                logging.getLogger(__name__).warning(f"Error closing session: {e}")


async def init_db() -> None:
    """
    Инициализация БД: создание всех таблиц (если не существуют).
    Используется при старте приложения.
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Корректное закрытие соединений с БД."""
    await async_engine.dispose()