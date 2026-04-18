import asyncio
import httpx
import websockets
import json
import uuid

API_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000"


async def test_short_id():
    """Тест для проверки функциональности short_id"""
    async with httpx.AsyncClient() as client:
        # 1. Создаём комнату и проверяем, что short_id генерируется
        print("\n=== Тест 1: Создание комнаты и получение short_id ===")
        room_id_str = str(uuid.uuid4())
        host_token = str(uuid.uuid4())
        response = await client.post(f"{API_URL}/api/rooms/", json={
            "room_id": room_id_str,
            "host_token": host_token,
            "status": "lobby",
            "totalPlayers": 8,
            "aiCount": 3,
            "peopleCount": 5,
            "roles": {
                "0": {"name": "Мирный", "count": 4, "canBeHuman": True, "canBeAI": True},
                "1": {"name": "Мафия", "count": 2, "canBeHuman": True, "canBeAI": True},
                "2": {"name": "Комиссар", "count": 1, "canBeHuman": True, "canBeAI": True},
                "3": {"name": "Доктор", "count": 1, "canBeHuman": True, "canBeAI": True}
            },
            "settings": {}
        })
        
        if response.status_code != 201:
            print(f"ERROR: Не удалось создать комнату: {response.text}")
            return None, None
        
        room_data = response.json()
        room_id = room_data["room_id"]
        short_id = room_data.get("short_id")
        
        print(f"OK: Комната создана: room_id={room_id}")
        print(f"OK: short_id получен: {short_id}")
        
        if not short_id:
            print("ERROR: short_id не был сгенерирован!")
            return None, None
        
        # Проверяем, что short_id имеет правильную длину
        if len(short_id) != 5:
            print(f"ERROR: Неверная длина short_id: {len(short_id)} (ожидалось 5)")
            return None, None
        
        print(f"OK: short_id имеет правильную длину: {len(short_id)}")
        
        # 2. Тест эндпоинта /s/{short_id} - редирект
        print("\n=== Тест 2: Эндпоинт /s/{short_id} редирект ===")
        response = await client.get(f"{API_URL}/api/rooms/s/{short_id}", follow_redirects=False)
        
        if response.status_code == 307:
            print(f"OK: Получен редирект (307): {response.headers.get('location', 'N/A')}")
        elif response.status_code == 200:
            print(f"OK: Эндпоинт работает (200)")
        else:
            print(f"ERROR: Ошибка редиректа: {response.status_code}")
        
        # 3. Тест получения комнаты по short_id
        print("\n=== Тест 3: Получение комнаты по short_id ===")
        response = await client.get(f"{API_URL}/api/rooms/{short_id}")
        
        if response.status_code == 200:
            room_by_short = response.json()
            print(f"OK: Комната получена по short_id: {room_by_short['room_id']}")
        else:
            print(f"ERROR: Не удалось получить комнату по short_id: {response.status_code}")
        
        # 4. Тест присоединения к комнате по short_id
        print("\n=== Тест 4: Присоединение к комнате по short_id ===")
        player_id_str = str(uuid.uuid4())
        response = await client.post(f"{API_URL}/api/rooms/{short_id}/join", json={
            "player_id": player_id_str,
            "room_id": room_data["id"],
            "nickname": "TestPlayer",
            "is_ai": False
        })
        
        if response.status_code == 200:
            player_data = response.json()
            print(f"OK: Игрок присоединился по short_id: {player_data['nickname']}")
        else:
            print(f"ERROR: Не удалось присоединиться по short_id: {response.text}")
        
        # 5. Тест получения списка игроков по short_id
        print("\n=== Тест 5: Получение списка игроков по short_id ===")
        response = await client.get(f"{API_URL}/api/rooms/{short_id}/players")
        
        if response.status_code == 200:
            players = response.json()
            print(f"OK: Получен список игроков: {len(players)} игроков")
        else:
            print(f"ERROR: Не удалось получить игроков: {response.status_code}")
        
        # 6. Тест обновления комнаты по short_id
        print("\n=== Тест 6: Обновление комнаты по short_id ===")
        response = await client.patch(f"{API_URL}/api/rooms/{short_id}", json={
            "totalPlayers": 10
        })
        
        if response.status_code == 200:
            updated_room = response.json()
            print(f"OK: Комната обновлена по short_id: totalPlayers={updated_room.get('totalPlayers')}")
        else:
            print(f"ERROR: Не удалось обновить комнату: {response.text}")
        
        return room_id, short_id


async def test_flow():
    """Основной тестовый поток"""
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ short_id")
    print("=" * 60)
    
    # Сначала тестируем short_id
    room_id, short_id = await test_short_id()
    
    if not short_id:
        print("\nERROR: Тестирование short_id не удалось. Завершаем.")
        return
    
    # Продолжаем с основным тестом
    async with httpx.AsyncClient() as client:
        # Используем short_id для присоединения
        print("\n=== Основной тест: Присоединение через short_id ===")
        
        # Присоединяемся к комнате по short_id
        player_id_str = str(uuid.uuid4())
        response = await client.post(f"{API_URL}/api/rooms/{short_id}/join", json={
            "player_id": player_id_str,
            "room_id": 0,  # Will be overridden by room lookup
            "nickname": "Player 1",
            "is_ai": False
        })
        
        if response.status_code != 200:
            print(f"ERROR: Не удалось присоединиться: {response.text}")
            return
        
        player1_data = response.json()
        player1_id = player1_data["id"]
        session_token = player1_data["session_token"]
        print(f"OK: Игрок 1 присоединился: {player1_id}, token: {session_token}")
        
        # Подключаемся через WebSocket
        print("\n=== WebSocket подключение ===")
        ws_url = f"{WS_URL}/ws/rooms/{short_id}?token={session_token}"
        
        try:
            async with websockets.connect(ws_url) as websocket:
                print("OK: WebSocket подключен!")
                
                # Запускаем игру
                print("Запуск игры...")
                await websocket.send(json.dumps({
                    "type": "start_game",
                    "data": {}
                }))
                
                # Ждём событие старта игры
                for _ in range(3):
                    msg = await websocket.recv()
                    print(f"Получено: {msg}")
                    data = json.loads(msg)
                    if data.get("type") == "game_started":
                        print("OK: Игра успешно запущена!")
                        break
        except Exception as e:
            print(f"ERROR: Ошибка WebSocket: {e}")
        
        # Тест получения game state по short_id
        print("\n=== Тест получения game state по short_id ===")
        response = await client.get(f"{API_URL}/api/rooms/{short_id}/game/state")
        
        if response.status_code == 200:
            game_state = response.json()
            print(f"OK: Получено состояние игры: phase={game_state.get('phase')}")
        else:
            print(f"WARN: Состояние игры недоступно: {response.status_code}")
        
        # Тест удаления комнаты по short_id
        print("\n=== Тест удаления комнаты по short_id ===")
        response = await client.delete(f"{API_URL}/api/rooms/{short_id}")
        
        if response.status_code == 204:
            print("OK: Комната удалена по short_id")
        else:
            print(f"ERROR: Не удалось удалить комнату: {response.status_code}")
        
        # Проверяем, что комната действительно удалена
        print("\n=== Проверка удаления ===")
        response = await client.get(f"{API_URL}/api/rooms/{short_id}")
        
        if response.status_code == 404:
            print("OK: Комната больше не существует")
        else:
            print(f"ERROR: Комната все еще существует: {response.status_code}")
    
    print("\n" + "=" * 60)
    print("ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_flow())
