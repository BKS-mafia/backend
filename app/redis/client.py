"""
Асинхронный клиент Redis для кэширования и pub/sub.
Использует redis.asyncio для асинхронных операций.
"""
from typing import Optional, Any, Union
import json
import pickle
from redis.asyncio import Redis, ConnectionPool
from redis.asyncio.client import Pipeline
from redis.exceptions import RedisError

from app.core.config import settings

# Глобальный пул подключений и клиент Redis
_redis_pool: Optional[ConnectionPool] = None
_redis_client: Optional[Redis] = None


async def get_redis() -> Redis:
    """
    Возвращает глобальный экземпляр асинхронного клиента Redis.
    Создаёт пул подключений при первом вызове.
    """
    global _redis_pool, _redis_client
    if _redis_client is not None:
        return _redis_client

    # Используем URL из настроек или собираем из параметров
    redis_url = str(settings.REDIS_URL) if settings.REDIS_URL else None
    if redis_url:
        _redis_pool = ConnectionPool.from_url(
            redis_url,
            decode_responses=False,  # возвращаем bytes для гибкости
            max_connections=10,
        )
    else:
        # Собираем параметры вручную
        _redis_pool = ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            decode_responses=False,
            max_connections=10,
        )

    _redis_client = Redis(connection_pool=_redis_pool)
    return _redis_client


async def close_redis() -> None:
    """Корректно закрывает пул подключений Redis."""
    global _redis_pool, _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
    if _redis_pool:
        await _redis_pool.disconnect()
        _redis_pool = None


# Утилиты для кэширования

async def cache_get(key: str, default: Any = None) -> Any:
    """
    Получить значение из кэша Redis.
    
    Args:
        key: Ключ Redis
        default: Значение по умолчанию, если ключ не найден
    
    Returns:
        Десериализованное значение или default
    """
    try:
        redis = await get_redis()
        data = await redis.get(key)
        if data is None:
            return default
        # Пытаемся декодировать как JSON, иначе как pickle
        try:
            return json.loads(data.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return pickle.loads(data)
    except RedisError:
        # В случае ошибки Redis возвращаем default
        return default


async def cache_set(
    key: str,
    value: Any,
    expire: Optional[int] = None,
    serialize: str = 'auto'
) -> bool:
    """
    Сохранить значение в кэш Redis.
    
    Args:
        key: Ключ Redis
        value: Значение для сохранения
        expire: TTL в секундах (None - без истечения)
        serialize: Метод сериализации ('json', 'pickle', 'auto')
    
    Returns:
        True в случае успеха, False при ошибке
    """
    try:
        redis = await get_redis()
        if serialize == 'json' or (serialize == 'auto' and isinstance(value, (dict, list, str, int, float, bool, type(None)))):
            data = json.dumps(value, ensure_ascii=False).encode('utf-8')
        else:
            data = pickle.dumps(value)
        
        if expire is not None:
            await redis.setex(key, expire, data)
        else:
            await redis.set(key, data)
        return True
    except RedisError:
        return False


async def cache_delete(key: str) -> bool:
    """
    Удалить ключ из кэша Redis.
    
    Returns:
        True если ключ удалён, False если ключа не было или ошибка
    """
    try:
        redis = await get_redis()
        result = await redis.delete(key)
        return result > 0
    except RedisError:
        return False


async def cache_keys(pattern: str = "*") -> list:
    """
    Получить список ключей, соответствующих шаблону.
    
    Args:
        pattern: Шаблон ключей (например, "user:*")
    
    Returns:
        Список ключей (bytes)
    """
    try:
        redis = await get_redis()
        return await redis.keys(pattern)
    except RedisError:
        return []


async def cache_clear_pattern(pattern: str = "*") -> int:
    """
    Удалить все ключи, соответствующие шаблону.
    
    Returns:
        Количество удалённых ключей
    """
    try:
        redis = await get_redis()
        keys = await redis.keys(pattern)
        if keys:
            await redis.delete(*keys)
        return len(keys)
    except RedisError:
        return 0


# Контекстный менеджер для транзакций (pipeline)
class RedisPipeline:
    """
    Контекстный менеджер для выполнения транзакций Redis (pipeline).
    
    Пример:
        async with RedisPipeline() as pipe:
            await pipe.set("key1", "value1")
            await pipe.set("key2", "value2")
            await pipe.execute()
    """
    def __init__(self):
        self.pipeline: Optional[Pipeline] = None
    
    async def __aenter__(self) -> Pipeline:
        redis = await get_redis()
        self.pipeline = redis.pipeline()
        return self.pipeline
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.pipeline:
            await self.pipeline.reset()