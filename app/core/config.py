"""
Конфигурация приложения на основе переменных окружения.
Использует pydantic_settings для загрузки и валидации.
"""
from typing import Optional, List
from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- OpenRouter API Configuration ---
    OPENROUTER_API_KEY: str = Field(
        description="API ключ для OpenRouter",
        default=""
    )
    DEFAULT_AI_MODEL: str = Field(
        description="Модель AI по умолчанию",
        default="openai/gpt-oss-120b:free"
    )
    OPENROUTER_BASE_URL: str = Field(
        description="Базовый URL OpenRouter API",
        default="https://openrouter.ai/api/v1"
    )

    # --- Application Settings ---
    ENVIRONMENT: str = Field(
        description="Окружение (development, production, testing)",
        default="development"
    )
    DEBUG: bool = Field(
        description="Режим отладки",
        default=True
    )
    SECRET_KEY: str = Field(
        description="Секретный ключ для подписи JWT",
        default="your_secret_key_here_change_in_production"
    )
    ALGORITHM: str = Field(
        description="Алгоритм подписи JWT",
        default="HS256"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        description="Время жизни access токена в минутах",
        default=30
    )

    # --- CORS Settings ---
    CORS_ORIGINS: List[str] = Field(
        description="Разрешённые origins для CORS",
        default=["http://localhost:3000", "http://localhost:8000"]
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        description="Разрешить учётные данные CORS",
        default=True
    )
    CORS_ALLOW_METHODS: List[str] = Field(
        description="Разрешённые HTTP методы",
        default=["*"]
    )
    CORS_ALLOW_HEADERS: List[str] = Field(
        description="Разрешённые HTTP заголовки",
        default=["*"]
    )

    # --- Database Configuration (PostgreSQL) ---
    POSTGRES_USER: str = Field(
        description="Пользователь PostgreSQL",
        default="postgres"
    )
    POSTGRES_PASSWORD: str = Field(
        description="Пароль PostgreSQL",
        default="postgres"
    )
    POSTGRES_DB: str = Field(
        description="Имя базы данных PostgreSQL",
        default="mafia"
    )
    POSTGRES_SERVER: str = Field(
        description="Хост PostgreSQL",
        default="db"
    )
    POSTGRES_PORT: int = Field(
        description="Порт PostgreSQL",
        default=5432
    )
    DATABASE_URL: Optional[PostgresDsn] = Field(
        description="Полный URL подключения к БД (asyncpg)",
        default=None
    )
    SQL_ECHO: bool = Field(
        description="Логирование SQL запросов",
        default=False
    )

    # --- Redis Configuration ---
    REDIS_HOST: str = Field(
        description="Хост Redis",
        default="redis"
    )
    REDIS_PORT: int = Field(
        description="Порт Redis",
        default=6379
    )
    REDIS_DB: int = Field(
        description="Номер базы Redis",
        default=0
    )
    REDIS_PASSWORD: Optional[str] = Field(
        description="Пароль Redis (если требуется)",
        default=None
    )
    REDIS_URL: Optional[RedisDsn] = Field(
        description="Полный URL подключения к Redis",
        default=None
    )

    # --- WebSocket Settings ---
    WEBSOCKET_TIMEOUT: int = Field(
        description="Таймаут WebSocket соединения в секундах",
        default=300
    )
    WEBSOCKET_MAX_SIZE: int = Field(
        description="Максимальный размер сообщения WebSocket в байтах",
        default=2 ** 20  # 1 MB
    )
    WEBSOCKET_HEARTBEAT_INTERVAL: int = Field(
        description="Интервал heartbeat в секундах",
        default=30
    )
    WEBSOCKET_MAX_CONNECTIONS_PER_ROOM: int = Field(
        description="Максимальное количество WebSocket соединений на комнату",
        default=50
    )

    # --- Game Settings ---
    MAX_PLAYERS_PER_ROOM: int = Field(
        description="Максимальное количество игроков в комнате",
        default=10
    )
    MIN_PLAYERS_TO_START: int = Field(
        description="Минимальное количество игроков для начала игры",
        default=5
    )
    GAME_TIMEOUT_SECONDS: int = Field(
        description="Таймаут игры в секундах",
        default=300
    )
    AI_RESPONSE_DELAY_MIN: int = Field(
        description="Минимальная задержка ответа AI в секундах",
        default=1
    )
    AI_RESPONSE_DELAY_MAX: int = Field(
        description="Максимальная задержка ответа AI в секундах",
        default=5
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Вычисляем DATABASE_URL если не задан явно
        if self.DATABASE_URL is None:
            self.DATABASE_URL = PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_SERVER,
                port=self.POSTGRES_PORT,
                path=self.POSTGRES_DB,
            )
        # Вычисляем REDIS_URL если не задан явно
        if self.REDIS_URL is None:
            scheme = "redis"
            if self.REDIS_PASSWORD:
                self.REDIS_URL = RedisDsn.build(
                    scheme=scheme,
                    username="",
                    password=self.REDIS_PASSWORD,
                    host=self.REDIS_HOST,
                    port=self.REDIS_PORT,
                    path=str(self.REDIS_DB),
                )
            else:
                self.REDIS_URL = RedisDsn.build(
                    scheme=scheme,
                    host=self.REDIS_HOST,
                    port=self.REDIS_PORT,
                    path=str(self.REDIS_DB),
                )

    @property
    def is_production(self) -> bool:
        """Проверка, что окружение production."""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Проверка, что окружение development."""
        return self.ENVIRONMENT.lower() == "development"

    @property
    def is_testing(self) -> bool:
        """Проверка, что окружение testing."""
        return self.ENVIRONMENT.lower() == "testing"


# Глобальный экземпляр настроек
settings = Settings()