"""
Главный модуль FastAPI приложения AI Mafia.
Содержит инициализацию приложения, настройки, подключение к БД и Redis,
регистрацию роутеров, WebSocket эндпоинтов, middleware и обработчиков ошибок.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
import uvicorn

from app.core.config import settings
from app.db.session import init_db, close_db
from app.redis.client import close_redis
from app.api.rooms import router as rooms_router
from app.api.players import router as players_router
from app.api.auth import router as auth_router
from app.websocket.handlers import router as websocket_router
from app.websocket.manager import manager
from app.models import *  # Импорт всех моделей для регистрации в SQLAlchemy

# Настройка логгера
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifespan менеджер для управления жизненным циклом приложения.
    Выполняет инициализацию БД и Redis при старте, закрытие при остановке.
    """
    logger.info("Starting application...")

    # Инициализация БД (создание таблиц, если не существуют)
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    # Подключаемся к Redis (ленивая инициализация при первом запросе)
    # Можно проверить подключение, вызвав get_redis
    from app.redis.client import get_redis
    try:
        redis_client = await get_redis()
        await redis_client.ping()
        logger.info("Redis connection established")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise

    yield

    logger.info("Shutting down application...")

    # Закрываем соединения с Redis
    await close_redis()
    logger.info("Redis connections closed")

    # Закрываем соединения с БД
    await close_db()
    logger.info("Database connections closed")


# Создание экземпляра FastAPI с lifespan
app = FastAPI(
    title="AI Mafia Backend",
    description="Backend для игры в мафию с AI игроками",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

# Настройка CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Регистрация роутеров API
app.include_router(rooms_router, prefix="/api/rooms", tags=["rooms"])
app.include_router(players_router, prefix="/api/players", tags=["players"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

# Регистрация WebSocket роутера
app.include_router(websocket_router, tags=["websocket"])


# Кастомные обработчики ошибок
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Обработчик HTTP исключений."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Обработчик ошибок валидации запроса."""
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append({"field": field, "message": error["msg"], "type": error["type"]})
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "errors": errors},
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """Обработчик ошибок валидации Pydantic."""
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append({"field": field, "message": error["msg"], "type": error["type"]})
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Pydantic validation error", "errors": errors},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Обработчик непредвиденных исключений."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# Эндпоинт проверки здоровья
@app.get("/health", tags=["health"])
async def health_check():
    """
    Проверка состояния приложения.
    Возвращает статус работы сервиса и версию.
    """
    from app.redis.client import get_redis
    from app.db.session import AsyncSessionLocal
    from sqlalchemy import text

    # Проверка подключения к БД
    db_ok = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as e:
        logger.exception("Database health check failed")

    # Проверка подключения к Redis
    redis_ok = False
    try:
        redis_client = await get_redis()
        await redis_client.ping()
        redis_ok = True
    except Exception as e:
        logger.exception("Redis health check failed")

    return {
        "status": "ok",
        "version": app.version,
        "database": "connected" if db_ok else "disconnected",
        "redis": "connected" if redis_ok else "disconnected",
    }


@app.get("/", tags=["root"])
async def root():
    """Корневой эндпоинт с информацией о приложении."""
    return {
        "message": "AI Mafia Backend API",
        "docs": "/docs",
        "health": "/health",
    }


# Экспорт глобального менеджера WebSocket
app.state.websocket_manager = manager


# Прямой запуск через uvicorn (для разработки)
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info" if settings.DEBUG else "warning",
    )