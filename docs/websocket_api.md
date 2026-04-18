# WebSocket API Documentation

Документация по WebSocket API для игры "Мафия". Здесь описаны все события, структуры данных и примеры использования для frontend разработчиков.

---

## Содержание

1. [Подключение к WebSocket](#подключение-к-websocket)
2. [Входящие события (сервер → клиент)](#входящие-события-сервер--клиент)
3. [Исходящие события (клиент → сервер)](#исходящие-события-клиент--сервер)
4. [Система чатов](#система-чатов)
5. [Фазы игры](#фазы-игры)

---

## Подключение к WebSocket

### URL подключения

```
ws://host:port/ws/rooms/{room_id}?token={player_token}
```

**Параметры:**

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `room_id` | string | Да | UUID комнаты |
| `token` | string | Да | Сессионный токен игрока |

### Пример подключения на JavaScript

```javascript
class WebSocketClient {
    constructor(roomId, token) {
        this.roomId = roomId;
        this.token = token;
        this.ws = null;
        this.listeners = new Map();
    }

    connect() {
        const url = `ws://localhost:8000/ws/rooms/${this.roomId}?token=${this.token}`;
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
        };

        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
        };
    }

    handleMessage(message) {
        const eventType = message.type || message.event;
        const handlers = this.listeners.get(eventType);
        
        if (handlers) {
            handlers.forEach(handler => handler(message));
        }
    }

    on(eventType, handler) {
        if (!this.listeners.has(eventType)) {
            this.listeners.set(eventType, []);
        }
        this.listeners.get(eventType).push(handler);
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
        }
    }
}

// Использование
const client = new WebSocketClient('room-uuid-123', 'player-token-abc');
client.connect();

// Подписка на события
client.on('player_joined', (msg) => {
    console.log('Игрок присоединился:', msg);
});

client.on('chat_message', (msg) => {
    console.log('Новое сообщение:', msg.content);
});
```

---

## Входящие события (сервер → клиент)

События, которые сервер отправляет клиенту.

### player_joined

Игрок присоединился к комнате.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "player_joined",
    "player_id": 123,
    "nickname": "PlayerName",
    "is_ai": false,
    "room_id": 1
}
```

**Поля:**

| Поле | Тип | Описание |
|------|-----|----------|
| `type` | string | Тип события |
| `player_id` | int | ID игрока |
| `nickname` | string | Никнейм игрока |
| `is_ai` | boolean | Является ли игрок AI |
| `room_id` | int | ID комнаты |

---

### player_left

Игрок покинул комнату.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "player_left",
    "player_id": 123,
    "nickname": "PlayerName"
}
```

---

### player_disconnected

Игрок отключился от WebSocket (но остался в игре).

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "player_disconnected",
    "player_id": 123,
    "nickname": "PlayerName"
}
```

---

### player_reconnected

Игрок переподключился к игре.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "player_reconnected",
    "player_id": 123,
    "nickname": "PlayerName"
}
```

---

### game_started

Игра началась.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "game_started",
    "room_id": 1,
    "game_id": 1,
    "message": "Игра началась! Распределение ролей..."
}
```

---

### game_phase_changed / phase_changed

Смена фазы игры.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "event": "phase_changed",
    "data": {
        "phase": "night",
        "day_number": 1
    }
}
```

**Доступные фазы:**

| Фаза | Описание |
|------|----------|
| `lobby` | Ожидание игроков |
| `night` | Ночная фаза |
| `day` | Дневная фаза |
| `voting` | Голосование |
| `turing_test` | Тест Тьюринга |
| `finished` | Игра окончена |

---

### role_assigned

Роль назначена игроку.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "role_assigned",
    "player_id": 123,
    "role": "mafia",
    "day_number": 1,
    "message": "Ваша роль: mafia"
}
```

**Доступные роли:**

| Роль | Описание |
|------|----------|
| `civilian` | Мирный житель |
| `mafia` | Мафия |
| `doctor` | Доктор |
| `commissioner` | Комиссар |

---

### night_started

Началась ночная фаза.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "night_started",
    "phase": "night",
    "day_number": 1,
    "message": "Наступила ночь. Мафия, доктор и комиссар выбирают жертв..."
}
```

---

### day_started

Началась дневная фаза.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "day_started",
    "event": "phase_changed",
    "data": {
        "phase": "day",
        "day_number": 1
    }
}
```

---

### voting_started

Началось голосование.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "voting_started",
    "event": "phase_changed",
    "data": {
        "phase": "voting"
    }
}
```

---

### vote_started

Началось голосование (альтернативное событие).

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "vote_started",
    "room_id": 1,
    "message": "Началось голосование!"
}
```

---

### vote_ended

Голосование закончилось.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "vote_ended",
    "room_id": 1,
    "eliminated_player_id": 123,
    "vote_count": {
        "123": 5,
        "124": 2
    }
}
```

---

### vote_received

Получен новый голос (обновление в реальном времени).

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "vote_received",
    "voter_id": 123,
    "target_player_id": 456
}
```

---

### vote_update

Обновление голосов во время голосования.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "vote_update",
    "votes": {
        "123": 5,
        "124": 2,
        "125": 1
    },
    "voters": {
        "123": 456,
        "124": 457,
        "125": 458
    }
}
```

---

### night_action_required

Требуется ночное действие (для ролей с особыми способностями).

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "night_action_required",
    "role": "mafia",
    "message": "Выберите игрока для убийства"
}
```

---

### night_action_accepted

Ночное действие принято.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "night_action_accepted",
    "player_id": 123,
    "action_type": "kill",
    "target_player_id": 456
}
```

---

### player_eliminated

Игрок исключён из игры.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "event": "player_eliminated",
    "type": "player_eliminated",
    "data": {
        "player_id": 123,
        "nickname": "PlayerName",
        "role": "mafia",
        "reason": "voted_out",
        "day_number": 2
    }
}
```

**Поля:**

| Поле | Тип | Описание |
|------|-----|----------|
| `player_id` | int | ID исключённого игрока |
| `nickname` | string | Никнейм игрока |
| `role` | string | Роль игрока |
| `reason` | string | Причина: `voted_out`, `killed` |
| `day_number` | int | Номер дня |

---

### you_died

Игрок умер.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "event": "you_died",
    "data": {
        "message": "You have died. You can now chat with other dead players.",
        "ghost_chat_enabled": true
    }
}
```

---

### turing_test_started

Начался Turing Test.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "event": "turing_test_started",
    "data": {
        "players": [
            {"id": 1, "nickname": "Player1", "is_ai": false},
            {"id": 2, "nickname": "Player2", "is_ai": true}
        ],
        "duration": 60
    }
}
```

---

### turing_test_results

Результаты Turing Test.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "event": "turing_test_results",
    "data": {
        "correct_guesses": 3,
        "total_ai_players": 2,
        "detection_accuracy": 0.75
    }
}
```

---

### turing_test_result

Результат Turing Test (альтернативное событие).

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "turing_test_result",
    "results": {
        "detected_ai": [2, 5],
        "missed_ai": [3],
        "accuracy": 0.66
    }
}
```

---

### game_over / game_ended

Игра окончена.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "game_over",
    "event": "game_over",
    "data": {
        "winner": "mafia"
    }
}
```

**Возможные победители:**

| Победитель | Описание |
|------------|----------|
| `mafia` | Победила мафия |
| `civilians` | Победили мирные |
| `aborted` | Игра прервана |

---

### chat_message

Сообщение в общий чат.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "chat_event",
    "player_id": 123,
    "nickname": "PlayerName",
    "content": "Привет всем!",
    "is_ai": false,
    "is_mafia_channel": false
}
```

---

### chat_message_extended

Сообщение в расширенный чат (cityGroup, mafiaGroup, roleChat).

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "chat_event_extended",
    "chatName": "cityGroup",
    "body": "Привет!",
    "player_id": 123,
    "nickname": "PlayerName",
    "is_ai": false
}
```

---

### ghost_chat_message

Сообщение в чат мёртвых.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "event": "ghost_chat_message",
    "data": {
        "sender_id": 123,
        "sender_name": "Ghost_Player",
        "content": "Привет из загробного мира!",
        "is_ghost": true
    }
}
```

---

### investigation_result

Результат расследования комиссара.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "investigation_result",
    "target_id": 456,
    "target_role": "mafia",
    "is_mafia": true
}
```

---

### error

Ошибка от сервера.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "error": "Сообщение об ошибке"
}
```

или

```json
{
    "event": "error",
    "data": {
        "message": "Сообщение об ошибке"
    }
}
```

---

### reconnect_state

Состояние игры при переподключении.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "reconnect_state",
    "player_id": 123,
    "nickname": "PlayerName",
    "role": "mafia",
    "is_alive": true,
    "room_id": 1,
    "game_id": 1,
    "game_status": "active",
    "phase": "day",
    "day_number": 2,
    "players": [
        {
            "id": 123,
            "nickname": "PlayerName",
            "is_alive": true,
            "is_ai": false,
            "is_connected": true
        }
    ]
}
```

---

### all_players_ready

Все игроки готовы к началу игры.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "all_players_ready",
    "room_id": 1,
    "ready_count": 8,
    "total_count": 8
}
```

---

### player_ready

Игрок отметился готовым.

**Направление:** Сервер → Клиент

**Структура данных:**

```json
{
    "type": "player_ready",
    "player_id": 123,
    "nickname": "PlayerName"
}
```

---

## Исходящие события (клиент → сервер)

События, которые клиент отправляет серверу.

### chat_message

Отправить сообщение в общий чат.

**Направление:** Клиент → Сервер

**Структура данных:**

```json
{
    "type": "chat_message",
    "content": "Привет всем!"
}
```

**Поля:**

| Поле | Тип | Обязательный | Описание |
|------|-----|--------------|----------|
| `type` | string | Да | Тип события |
| `content` | string | Да | Текст сообщения |

**Ограничения:**

- Ночью только мафия может писать в чат
- Мёртвые игроки автоматически перенаправляются в Ghost Chat

---

### chat_message_extended

Отправить сообщение в расширенный чат.

**Направление:** Клиент → Сервер

**Структура данных:**

```json
{
    "type": "chat_message_extended",
    "chatName": "cityGroup",
    "body": "Привет!",
    "roomId": "room-uuid-123"
}
```

**Поля:**

| Поле | Тип | Обязательный | Описание |
|------|-----|--------------|----------|
| `type` | string | Да | Тип события |
| `chatName` | string | Да | Название чата: `cityGroup`, `mafiaGroup`, `roleChat` |
| `body` | string | Да | Текст сообщения |
| `roomId` | string | Нет | ID комнаты |

---

### ghost_chat

Отправить сообщение в чат мёртвых.

**Направление:** Клиент → Сервер

**Структура данных:**

```json
{
    "type": "ghost_chat",
    "content": "Привет из загробного мира!"
}
```

**Ограничения:** Только для мёртвых игроков.

---

### vote_action

Голосовать за игрока.

**Направление:** Клиент → Сервер

**Структура данных:**

```json
{
    "type": "vote_action",
    "target_player_id": 456
}
```

**Поля:**

| Поле | Тип | Обязательный | Описание |
|------|-----|--------------|----------|
| `type` | string | Да | Тип события |
| `target_player_id` | int | Да | ID игрока, за которого голосуем |

**Также используется для ночных действий:**

```json
{
    "type": "vote_action",
    "target_player_id": 456,
    "action_type": "kill"
}
```

**Типы действий (ночная фаза):**

| Тип | Описание | Доступно для |
|-----|----------|--------------|
| `kill` | Убить игрока | Мафия |
| `heal` | Вылечить игрока | Доктор |
| `investigate` | Расследовать игрока | Комиссар |

---

### night_action

Ночное действие (альтернативный способ отправки).

**Направление:** Клиент → Сервер

**Структура данных:**

```json
{
    "type": "night_action",
    "action_type": "kill",
    "target_player_id": 456
}
```

**Поля:**

| Поле | Тип | Обязательный | Описание |
|------|-----|--------------|----------|
| `type` | string | Да | Тип события |
| `action_type` | string | Да | Тип действия: `kill`, `heal`, `check` |
| `target_player_id` | int | Да | ID целевого игрока |

---

### start_game

Начать игру (только для хоста).

**Направление:** Клиент → Сервер

**Структура данных:**

```json
{
    "type": "start_game"
}
```

**Требования:**

- Только хост комнаты может начать игру
- Все игроки должны быть в комнате

---

### ready

Отметиться готовым к началу игры.

**Направление:** Клиент → Сервер

**Структура данных:**

```json
{
    "type": "ready"
}
```

---

### reconnect

Переподключиться к игре после разрыва соединения.

**Направление:** Клиент → Сервер

**Структура данных:**

```json
{
    "type": "reconnect",
    "session_token": "uuid-token"
}
```

---

### kick_player

Исключить игрока из комнаты (только для хоста).

**Направление:** Клиент → Сервер

**Структура данных:**

```json
{
    "type": "kick_player",
    "player_id": 123
}
```

---

### turing_test_vote

Голосование в Turing Test.

**Направление:** Клиент → Сервер

**Структура данных:**

```json
{
    "type": "turing_test_vote",
    "suspected_ai_ids": [2, 5, 8]
}
```

**Поля:**

| Поле | Тип | Обязательный | Описание |
|------|-----|--------------|----------|
| `type` | string | Да | Тип события |
| `suspected_ai_ids` | array | Да | Массив ID игроков, которых игрок подозревает в том, что они AI |

---

## Система чатов

В игре реализовано 4 типа чатов:

### 1. Общий чат (chat_message)

- **Когда работает:** Всегда, кроме ночи для не-мафии
- **Ночью:** Только для мафии (приватный канал)
- **После смерти:** Автоматически перенаправляется в Ghost Chat

### 2. cityGroup

- **Когда работает:** Дневная фаза (DAY), фаза голосования (VOTING), Turing Test
- **Кто может писать:** Все живые игроки
- **Кто видит:** Все живые игроки

**Пример отправки:**

```javascript
client.send({
    "type": "chat_message_extended",
    "chatName": "cityGroup",
    "body": "Давайте голосовать против игрока X!"
});
```

### 3. mafiaGroup

- **Когда работает:** Ночная фаза (NIGHT)
- **Кто может писать:** Только игроки с ролью `mafia`
- **Кто видит:** Все живые игроки-мафиози

**Пример отправки:**

```javascript
client.send({
    "type": "chat_message_extended",
    "chatName": "mafiaGroup",
    "body": "Убиваем игрока X сегодня"
});
```

### 4. roleChat

- **Когда работает:** Ночная фаза (NIGHT)
- **Кто может писать:** Только игроки с ролью `doctor` или `commissioner`
- **Кто видит:** Доктор и комиссар

**Пример отправки:**

```javascript
client.send({
    "type": "chat_message_extended",
    "chatName": "roleChat",
    "body": "Я проверю игрока X этой ночью"
});
```

### 5. Ghost Chat

- **Когда работает:** После смерти игрока
- **Кто может писать:** Только мёртвые игроки
- **Кто видит:** Все мёртвые игроки и зрители

**Пример отправки:**

```javascript
client.send({
    "type": "ghost_chat",
    "content": "Меня убили на 3 день..."
});
```

---

## Фазы игры

### LOBBY (Ожидание)

- Игроки присоединяются к комнате
- Хост может начать игру когда все на месте
- Все игроки должны нажать "Готов"

### NIGHT (Ночь)

- Активны роли: Mafia, Doctor, Commissioner
- MafiaGroup и roleChat доступны
- Обычный чат отключён для не-мафии

### DAY (День)

- Все игроки могут общаться в cityGroup
- Общий чат работает для всех
- Игроки обсуждают кандидатов на исключение

### VOTING (Голосование)

- Игроки голосуют за исключение кандидата
- vote_action используется для голосования

### TURING_TEST (Тест Тьюринга)

- После окончания игры
- Игроки угадывают, кто из оставшихся был AI
- turing_test_vote для голосования

### FINISHED (Игра окончена)

- Определён победитель
- Показаны результаты Turing Test

---

## Примеры использования

### Полный цикл игры

```javascript
// 1. Подключение
const client = new WebSocketClient('room-uuid', 'token');
client.connect();

// 2. Ожидание начала игры
client.on('player_joined', (msg) => {
    updatePlayerList(msg);
});

client.on('all_players_ready', (msg) => {
    console.log('Все готовы, игра скоро начнётся');
});

// 3. Начало игры
client.on('game_started', (msg) => {
    console.log('Игра началась!');
});

client.on('role_assigned', (msg) => {
    console.log('Ваша роль:', msg.role);
    showRoleCard(msg.role);
});

// 4. Ночная фаза
client.on('night_started', (msg) => {
    if (myRole === 'mafia' || myRole === 'doctor' || myRole === 'commissioner') {
        showNightActionUI();
    }
});

client.on('night_action_required', (msg) => {
    showActionPrompt(msg.role);
});

// 5. Дневная фаза
client.on('day_started', (msg) => {
    showDayDiscussion();
});

client.on('voting_started', (msg) => {
    showVotingUI();
});

// 6. Голосование
client.on('vote_update', (msg) => {
    updateVoteCounts(msg.votes);
});

// 7. Исключение игрока
client.on('player_eliminated', (msg) => {
    showElimination(msg);
});

// 8. Конец игры
client.on('game_over', (msg) => {
    showWinner(msg.data.winner);
});

client.on('turing_test_started', (msg) => {
    showTuringTestUI(msg.data.players);
});
```

### Обработка ошибок

```javascript
client.on('error', (msg) => {
    if (msg.error) {
        showNotification(msg.error, 'error');
    } else if (msg.data && msg.data.message) {
        showNotification(msg.data.message, 'error');
    }
});

// Также можно слушать конкретные ошибки
client.on('vote_accepted', (msg) => {
    console.log('Голос принят');
});
```

---

## Коды ошибок WebSocket

| Код | Описание |
|-----|----------|
| 1000 | Нормальное закрытие |
| 1001 | Клиент покинул |
| 1008 | Нарушение политики (неверный токен) |
| 1011 | Внутренняя ошибка сервера |

---

## Рекомендации по реализации

1. **Автоматическое переподключение:** Реализуйте механизм переподключения при разрыве соединения
2. **Очередь сообщений:** Накапливайте исходящие сообщения при отсутствии соединения
3. **Heartbeat:** Реализуйте периодическую проверку соединения
4. **Обработка состояний:** Всегда проверяйте текущую фазу игры перед отправкой действий
5. **Валидация:** Проверяйте данные на клиенте перед отправкой на сервер