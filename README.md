# Mafia AI Agents

Многопользовательская онлайн-игра «Мафия» с AI-агентами, управляемыми через OpenRouter API. Погрузитесь в классическую детективную игру, где игроки-люди соревнуются с интеллектуальными AI-персонажами.

---

## Описание проекта

**Mafia AI Agents** — это backend-приложение для популярной настольной игры «Мафия», разработанное на Python с использованием FastAPI. Проект позволяет создавать игровые комнаты, присоединяться к ним игрокам и играть вместе с AI-агентами, которые используют современные языковые модели для реалистичного поведения.

### Основные возможности

- **Создание игровых комнат** — создавайте публичные или приватные лобби с настраиваемыми параметрами
- **AI-агенты** — играйте вместе с интеллектуальными ботами, использующими OpenRouter API (поддержка различных LLM)
- **Real-time коммуникация** — мгновенный обмен сообщениями через WebSocket
- **Система ролей** — классические роли: Мафия, Доктор, Комиссар, Мирный житель
- **Голосования и дискуссии** — механика дневных и ночных фаз игры
- **Приватные чаты** — коммуникация между членами мафии и один на один с доктором
- **REST API** — полноценный API для управления комнатами и игроками
- **Swagger документация** — интерактивная документация API

---

## Технологический стек

### Backend

- **Python 3.10+** — основной язык программирования
- **FastAPI** — веб-фреймворк для построения REST API и WebSocket
- **SQLAlchemy 2.0+** — ORM для работы с базой данных
- **Pydantic 2.0+** — валидация данных и схемы

### База данных

- **PostgreSQL** — основная база данных (в production)
- **SQLite** — доступна для разработки и тестирования

### Кэширование и очереди

- **Redis** — кэширование, Pub/Sub для real-time событий

### AI

- **OpenRouter API** — унифицированный API для доступа к различным LLM (Google Gemini, OpenAI, Anthropic и др.)

### Инфраструктура

- **Docker / Docker Compose** — контейнеризация приложения
- **uvicorn** — ASGI-сервер для запуска FastAPI

---

## Установка и запуск

### Требования

- Python 3.10 или выше
- Docker и Docker Compose (для запуска через Docker)
- PostgreSQL 15+ (при запуске без Docker)
- Redis 7+ (при запуске без Docker)

### Установка зависимостей

```bash
# Клонирование репозитория
git clone <repository-url>
cd backend

# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows

# Установка зависимостей
pip install -r requirements.txt
```

### Запуск через Docker

```bash
# Копирование файла переменных окружения
cp .env.example .env

# Запуск всех сервисов
docker-compose up -d

# Просмотр логов
docker-compose logs -f backend
```

После запуска доступны:

- Backend API: http://localhost:8000
- Swagger документация: http://localhost:8000/docs
- ReDoc документация: http://localhost:8000/redoc

### Запуск напрямую (без Docker)

```bash
# Настройка переменных окружения
cp .env.example .env
# Отредактируйте .env файл, указав корректные параметры подключения к БД

# Запуск PostgreSQL и Redis (или используйте облачные сервисы)

# Инициализация базы данных
python scripts/init_db.py

# Запуск сервера
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Переменные окружения

Создайте файл `.env` на основе `.env.example`:

```env
# OpenRouter API Configuration
OPENROUTER_API_KEY=your_api_key_here
DEFAULT_AI_MODEL=google/gemini-2.5-flash-lite

# Application Settings
ENVIRONMENT=development
DEBUG=True
SECRET_KEY=your_secret_key_here_change_in_production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Database Configuration
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=mafia
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/mafia

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_URL=redis://localhost:6379/0

# Game Settings
MAX_PLAYERS_PER_ROOM=10
MIN_PLAYERS_TO_START=5
GAME_TIMEOUT_SECONDS=300
AI_RESPONSE_DELAY_MIN=1
AI_RESPONSE_DELAY_MAX=5
```

---

## Структура проекта

```
backend/
├── app/                      # Основной код приложения
│   ├── main.py              # Точка входа, инициализация FastAPI
│   ├── prompts.json         # Промпты для AI агентов
│   │
│   ├── api/                 # API эндпоинты
│   │   ├── __init__.py
│   │   ├── auth.py          # Аутентификация и авторизация
│   │   ├── players.py       # Управление игроками
│   │   └── rooms.py         # Управление комнатами
│   │
│   ├── models/              # Модели SQLAlchemy (БД)
│   │   ├── __init__.py
│   │   ├── base.py          # Базовый класс моделей
│   │   ├── game.py          # Модель игры
│   │   ├── game_event.py    # Модель игровых событий
│   │   ├── player.py        # Модель игрока
│   │   └── room.py          # Модель комнаты
│   │
│   ├── schemas/             # Pydantic схемы (валидация)
│   │   ├── __init__.py
│   │   ├── game.py          # Схемы для игры
│   │   ├── game_event.py    # Схемы для событий
│   │   ├── player.py        # Схемы для игроков
│   │   └── room.py          # Схемы для комнат
│   │
│   ├── crud/                # Операции с базой данных
│   │   ├── __init__.py
│   │   ├── game.py          # CRUD для игры
│   │   ├── game_event.py    # CRUD для событий
│   │   ├── player.py        # CRUD для игроков
│   │   └── room.py          # CRUD для комнат
│   │
│   ├── services/            # Бизнес-логика
│   │   ├── __init__.py
│   │   ├── ai_service.py    # Логика AI агентов
│   │   ├── game_service.py  # Управление игровым процессом
│   │   └── room_service.py  # Управление комнатами
│   │
│   ├── websocket/           # WebSocket обработчики
│   │   ├── __init__.py
│   │   ├── handlers.py      # Обработчики событий
│   │   └── manager.py       # Менеджер подключений
│   │
│   ├── db/                  # Работа с базой данных
│   │   ├── session.py       # Сессия SQLAlchemy
│   │
│   ├── redis/               # Работа с Redis
│   │   ├── client.py        # Клиент Redis
│   │
│   ├── core/                # Конфигурация
│   │   └── config.py        # Настройки приложения
│   │
│   ├── ai/                  # AI модули
│   │   ├── mcp_tools.py     # Инструменты для AI агентов
│   │   └── openrouter_client.py  # Клиент OpenRouter
│   │
│   ├── game/                # Игровая логика
│   │   └── state_machine.py # Машина состояний игры
│   │
│   └── utils/               # Утилиты
│       └── short_id.py      # Генератор коротких ID
│
├── docs/                    # Документация
│   └── websocket_api.md     # WebSocket API документация
│
├── scripts/                 # Скрипты
│   └── init_db.py          # Инициализация БД
│
├── tests/                   # Тесты
│   ├── test_ai_agents.py
│   ├── test_flow.py
│   ├── app.js
│   ├── index.html
│   └── style.css
│
├── docker/                  # Docker файлы
│   └── Dockerfile
│
├── docker-compose.yml       # Docker Compose конфигурация
├── requirements.txt         # Python зависимости
├── .env.example            # Пример переменных окружения
└── README.md               # Этот файл
```

---

## API эндпоинты

### Комнаты

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/api/rooms` | Получить список активных комнат |
| `POST` | `/api/rooms` | Создать новую комнату |
| `GET` | `/api/rooms/{room_id}` | Получить информацию о комнате |
| `DELETE` | `/api/rooms/{room_id}` | Удалить комнату |
| `POST` | `/api/rooms/{room_id}/join` | Присоединиться к комнате |
| `POST` | `/api/rooms/{room_id}/leave` | Покинуть комнату |
| `POST` | `/api/rooms/{room_id}/start` | Начать игру |
| `GET` | `/api/s/{short_id}` | Перенаправление по короткой ссылке |

### Игроки

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/api/players` | Создать игрока |
| `GET` | `/api/players/{player_id}` | Получить информацию об игроке |
| `PUT` | `/api/players/{player_id}` | Обновить данные игрока |
| `DELETE` | `/api/players/{player_id}` | Удалить игрока |

### Аутентификация

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/api/auth/login` | Вход в игру |
| `POST` | `/api/auth/logout` | Выход из игры |

### Документация

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc |
| `GET` | `/openapi.json` | OpenAPI спецификация |

---

## WebSocket

### URL подключения

```
ws://host:port/ws/rooms/{room_id}?token={player_token}
```

### Основные события

Полный список событий и их структура описаны в [docs/websocket_api.md](docs/websocket_api.md).

#### Входящие события (сервер → клиент)

- `player_joined` — игрок присоединился к комнате
- `player_left` — игрок покинул комнату
- `game_started` — игра началась
- `game_phase_changed` — смена фазы игры
- `role_assigned` — роль назначена игроку
- `vote_started` — началось голосование
- `vote_ended` — голосование завершено
- `player_killed` — игрок убит
- `player_saved` — игрок спасён
- `chat_message` — получено сообщение в чате
- `game_ended` — игра завершена

#### Исходящие события (клиент → сервер)

- `send_message` — отправить сообщение в чат
- `vote` — проголосовать за игрока
- `use_ability` — использовать способность (доктор/комиссар)
- `ready` — готовность к игре

---

## Игровые роли

| Роль | Команда | Описание |
|------|---------|----------|
| **Мафия (Mafia)** | Мафия | Знают друг друга. Каждую ночь убивают одного мирного жителя. Побеждают, когда число мафии равно или превышает число мирных. |
| **Доктор (Doctor)** | Мирные | Каждую ночь может защитить одного игрока (включая себя) от убийства. Знает, кого защитил этой ночью. |
| **Комиссар (Commissioner)** | Мирные | Каждую ночь может проверить одного игрока на принадлежность к мафии. Получает информацию о роли. |
| **Мирный житель (Civilian)** | Мирные | Обычные игроки без специальных способностей. Участвуют в дневных дискуссиях и голосованиях. |

### Правила победы

- **Мирные побеждают**, когда все члены мафии убиты
- **Мафия побеждает**, когда число мафии равно или превышает число мирных жителей

---

## Система чатов

В игре реализовано несколько каналов коммуникации:

### 1. Общий чат (cityGroup)

- **Доступ:** Все игроки (и живые, и мёртвые)
- **Описание:** Главный чат для общих дискуссий в дневное время

### 2. Чат мафии (mafiaGroup)

- **Доступ:** Только члены мафии
- **Описание:** Приватный чат для координации ночных убийств

### 3. Чат роли (roleChat)

- **Доступ:** Только игроки с особыми ролями
- **Описание:** Приватный чат для:
  - Доктора (общение с пациентом)
  - Комиссара (получение результатов проверок)

### Правила доступа к чатам

- В зависимости от фазы игры (день/ночь) доступны разные чаты
- Мёртвые игроки могут общаться только в общем чате
- AI агенты следуют правилам ролевой игры

---

## Конфигурация

### Основные параметры

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `ENVIRONMENT` | Режим работы (development/production) | development |
| `DEBUG` | Режим отладки | True |
| `SECRET_KEY` | Секретный ключ для JWT токенов | - |
| `ALGORITHM` | Алгоритм шифрования JWT | HS256 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Время жизни токена (минуты) | 30 |

### База данных

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `DATABASE_URL` | Строка подключения к PostgreSQL | postgresql+asyncpg://... |
| `POSTGRES_USER` | Имя пользователя БД | postgres |
| `POSTGRES_PASSWORD` | Пароль БД | postgres |
| `POSTGRES_DB` | Имя базы данных | mafia |

### Redis

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `REDIS_URL` | Строка подключения к Redis | redis://localhost:6379/0 |

### AI

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `OPENROUTER_API_KEY` | API ключ OpenRouter | - |
| `DEFAULT_AI_MODEL` | Модель LLM по умолчанию | google/gemini-2.5-flash-lite |
| `AI_RESPONSE_DELAY_MIN` | Минимальная задержка ответа AI (сек) | 1 |
| `AI_RESPONSE_DELAY_MAX` | Максимальная задержка ответа AI (сек) | 5 |

### Игра

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `MAX_PLAYERS_PER_ROOM` | Максимум игроков в комнате | 10 |
| `MIN_PLAYERS_TO_START` | Минимум игроков для старта | 5 |
| `GAME_TIMEOUT_SECONDS` | Таймаут игры (секунды) | 300 |

---

## Разработка

### Запуск тестов

```bash
# Установка тестовых зависимостей
pip install pytest pytest-asyncio

# Запуск всех тестов
pytest

# Запуск с покрытием
pytest --cov=app
```

### Структура API

Проект следует принципам чистой архитектуры:

- **API Layer** — обработка HTTP/WebSocket запросов
- **Service Layer** — бизнес-логика
- **CRUD Layer** — операции с базой данных
- **Model Layer** — модели SQLAlchemy
- **Schema Layer** — Pydantic схемы валидации

---

## Лицензия

MIT License

---

## Контакты

Для вопросов и предложений создавайте issue в репозитории проекта.