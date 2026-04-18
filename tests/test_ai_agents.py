"""
Тестовый скрипт для проверки работы ИИ агентов в игре "Мафия".
Запускает игру с полностью ИИ-игроками и отслеживает все этапы игры.

Использование:
    python tests/test_ai_agents.py [--players N] [--server URL]

Примеры:
    python tests/test_ai_agents.py
    python tests/test_ai_agents.py --players 6
    python tests/test_ai_agents.py --server http://91.201.252.14:8000
"""

import asyncio
import argparse
import json
import uuid
import sys
from datetime import datetime
from typing import Optional

import httpx


class AITestRunner:
    def __init__(self, server_url: str, total_players: int = 8):
        self.server_url = server_url.rstrip('/')
        self.total_players = total_players
        self.room_id: Optional[str] = None
        self.host_token: Optional[str] = None
        self.session_token: Optional[str] = None
        self.game_id: Optional[int] = None
        self.ws: Optional[httpx.AsyncClient] = None
        
        # Статистика
        self.events_received = []
        self.ai_messages = []
        self.night_actions = []
        self.votes = []
        
    async def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = {
            "INFO": "ℹ",
            "SUCCESS": "✓",
            "ERROR": "✗",
            "AI": "🤖",
            "GAME": "🎮"
        }.get(level, "•")
        print(f"[{timestamp}] {prefix} {message}")
    
    async def create_room(self) -> bool:
        """Создать комнату с ИИ-игроками."""
        self.room_id = str(uuid.uuid4())
        self.host_token = str(uuid.uuid4())
        
        payload = {
            "room_id": self.room_id,
            "host_token": self.host_token,
            "status": "lobby",
            "totalPlayers": self.total_players,
            "aiCount": self.total_players,
            "peopleCount": 0,
            "settings": {
                "showAIMessages": True
            }
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.server_url}/api/rooms/",
                    json=payload,
                    timeout=10.0
                )
                if response.status_code == 201:
                    data = response.json()
                    await self.log(f"Комната создана: {self.room_id}", "SUCCESS")
                    await self.log(f"  Всего игроков: {self.total_players} (все ИИ)", "INFO")
                    return True
                else:
                    await self.log(f"Ошибка создания комнаты: {response.text}", "ERROR")
                    return False
            except Exception as e:
                await self.log(f"Ошибка: {e}", "ERROR")
                return False
    
    async def join_room(self) -> bool:
        """Присоединиться к комнате как наблюдатель."""
        player_id = str(uuid.uuid4())
        payload = {
            "player_id": player_id,
            "room_id": 0,
            "nickname": "Test_Observer",
            "is_ai": False
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.server_url}/api/rooms/{self.room_id}/join",
                    json=payload,
                    timeout=10.0
                )
                if response.status_code in (200, 201):
                    data = response.json()
                    self.session_token = data.get("session_token")
                    await self.log(f"Присоединён к комнате", "SUCCESS")
                    return True
                else:
                    await self.log(f"Ошибка присоединения: {response.text}", "ERROR")
                    return False
            except Exception as e:
                await self.log(f"Ошибка: {e}", "ERROR")
                return False
    
    async def start_game(self) -> bool:
        """Запустить игру через HTTP API."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.server_url}/api/rooms/{self.room_id}/game/start",
                    timeout=30.0
                )
                if response.status_code == 200:
                    data = response.json()
                    self.game_id = data.get("game_id")
                    await self.log(f"Игра запущена! ID: {self.game_id}", "SUCCESS")
                    return True
                else:
                    await self.log(f"Ошибка запуска: {response.text}", "ERROR")
                    return False
            except Exception as e:
                await self.log(f"Ошибка: {e}", "ERROR")
                return False
    
    async def get_room_info(self):
        """Получить информацию о комнате."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.server_url}/api/rooms/{self.room_id}",
                    timeout=10.0
                )
                if response.status_code == 200:
                    return response.json()
            except:
                pass
        return None
    
    async def get_players(self):
        """Получить список игроков."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.server_url}/api/rooms/{self.room_id}/players",
                    timeout=10.0
                )
                if response.status_code == 200:
                    return response.json()
            except:
                pass
        return []

    async def get_game_state(self):
        """Получить состояние игры."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.server_url}/api/rooms/{self.room_id}/game/state",
                    timeout=10.0
                )
                if response.status_code == 200:
                    return response.json()
            except:
                pass
        return None

    async def get_game_events(self, limit: int = 50):
        """Получить события игры (сообщения, голосования, действия)."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.server_url}/api/rooms/{self.room_id}/game/events?limit={limit}",
                    timeout=10.0
                )
                if response.status_code == 200:
                    return response.json()
            except:
                pass
        return []

    async def get_player_name(self, players: list, player_id: int) -> str:
        """Получить имя игрока по ID."""
        for p in players:
            if p.get("id") == player_id:
                return p.get("nickname", f"Player_{player_id}")
        return f"Player_{player_id}"
    
    async def run(self):
        """Основной метод запуска теста."""
        await self.log("=" * 50, "INFO")
        await self.log("Тест ИИ-агентов Мафии", "INFO")
        await self.log(f"Сервер: {self.server_url}", "INFO")
        await self.log(f"Игроков: {self.total_players} (все ИИ)", "INFO")
        await self.log("=" * 50, "INFO")
        
        # 1. Создаём комнату
        await self.log("\n[1/4] Создание комнаты...", "INFO")
        if not await self.create_room():
            return
        
        # 2. Присоединяемся
        await self.log("\n[2/4] Присоединение к комнате...", "INFO")
        if not await self.join_room():
            return
        
        # 3. Запускаем игру
        await self.log("\n[3/4] Запуск игры...", "INFO")
        if not await self.start_game():
            return
        
        # 4. Мониторим игру
        await self.log("\n[4/4] Мониторинг игры (ожидание 60 сек)...", "INFO")
        await self.monitor_game()
        
        # Итоги
        await self.print_summary()
    
    async def monitor_game(self):
        """Мониторинг игры в течение указанного времени."""
        start_time = asyncio.get_event_loop().time()
        duration = 90  # секунд
        shown_event_ids = set()  # Отслеживаем уже показанные события
        
        while asyncio.get_event_loop().time() - start_time < duration:
            await asyncio.sleep(5)
            
            # Получаем состояние игры
            state = await self.get_game_state()
            if state:
                phase = state.get("phase", "unknown")
                day = state.get("day_number", 0)
                alive = state.get("alive_count", 0)
                
                await self.log(f"День {day}, фаза: {phase}, живых: {alive}", "GAME")
                
                # Проверяем завершение игры
                if phase == "finished" or phase == "turing_test":
                    await self.log("Игра завершена!", "SUCCESS")
                    break
            
            # Получаем события игры (сообщения, голосования, действия)
            events = await self.get_game_events(limit=100)
            if events:
                players = await self.get_players()
                # Показываем только новые события (которые ещё не показывали)
                for event in reversed(events):
                    event_id = event.get("id")
                    if event_id in shown_event_ids:
                        continue
                    shown_event_ids.add(event_id)
                    
                    event_type = event.get("event_type", "")
                    event_data = event.get("event_data", {})
                    player_id = event.get("player_id")
                    player_name = await self.get_player_name(players, player_id) if players else f"Player_{player_id}"
                    
                    if event_type in ("chat", "chat_mafia"):
                        # Сообщение в чате
                        content = event_data.get("content", "")
                        if content:
                            chat_type = "[МАФИЯ]" if event_type == "chat_mafia" else ""
                            await self.log(f"  {player_name}{chat_type}: {content}", "CHAT")
                    
                    elif event_type == "vote":
                        # Голосование
                        target_id = event_data.get("target_player_id")
                        target_name = await self.get_player_name(players, target_id) if players else f"Player_{target_id}"
                        await self.log(f"  -> {player_name} проголосовал за {target_name}", "VOTE")
                    
                    elif event_type in ("night_action", "action"):
                        # Ночное действие
                        action_type = event_data.get("action_type", "unknown")
                        target_id = event_data.get("target_player_id")
                        target_name = await self.get_player_name(players, target_id) if players else f"Player_{target_id}"
                        
                        action_desc = {
                            "kill": "убил",
                            "heal": "вылечил",
                            "investigate": "проверил"
                        }.get(action_type, action_type)
                        
                        await self.log(f"  -> {player_name} {action_desc} {target_name} (ночь)", "ACTION")
                    
                    elif event_type == "eliminated":
                        # Игрок eliminated
                        await self.log(f"  !! {player_name} был eliminated", "ELIMINATED")
            
            # Проверяем игроков
            players = await self.get_players()
            if players:
                ai_count = sum(1 for p in players if p.get("is_ai"))
                alive_count = sum(1 for p in players if p.get("is_alive"))
                await self.log(f"  ИИ-игроков: {ai_count}, живых: {alive_count}", "INFO")
    
    async def print_summary(self):
        """Вывод итогов тестирования."""
        await self.log("\n" + "=" * 50, "INFO")
        await self.log("Итоги тестирования:", "INFO")
        await self.log("=" * 50, "INFO")
        
        # Получаем финальное состояние
        state = await self.get_game_state()
        if state:
            await self.log(f"Фаза: {state.get('phase', 'unknown')}", "INFO")
            await self.log(f"День: {state.get('day_number', 0)}", "INFO")
            await self.log(f"Живых: {state.get('alive_count', 0)}", "INFO")
        
        players = await self.get_players()
        if players:
            await self.log(f"\nВсего игроков: {len(players)}", "INFO")
            for p in players:
                role = p.get("role", "unknown")
                status = " alive" if p.get("is_alive") else " dead"
                ai = " [ИИ]" if p.get("is_ai") else ""
                await self.log(f"  {p.get('nickname')}: {role}{status}{ai}", "INFO")


async def main():
    parser = argparse.ArgumentParser(description="Тест ИИ-агентов Мафии")
    parser.add_argument(
        "--server", 
        default="http://localhost:8000",
        help="URL сервера"
    )
    parser.add_argument(
        "--players", 
        type=int, 
        default=8,
        help="Количество игроков"
    )
    
    args = parser.parse_args()
    
    runner = AITestRunner(args.server, args.players)
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())