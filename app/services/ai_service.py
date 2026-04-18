"""
Сервис для взаимодействия с OpenRouter API (использовать app.ai.openrouter_client).
Генерация ответов AI в зависимости от роли и контекста.
Управление "характерами" AI (prompt-профили).
Имитация набора текста (типинг) и задержки ответов.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from app.ai.openrouter_client import OpenRouterClient
from app.ai.mcp_tools import (
    DAY_TOOLS,
    NIGHT_TOOLS,
    VOTE_TOOLS,
    MCPToolDispatcher,
)

logger = logging.getLogger(__name__)


@dataclass
class AICharacter:
    """
    Профиль персонажа AI.
    """
    name: str
    role: str  # "mafia", "civilian", "doctor", "commissioner"
    personality: str  # описание характера
    speaking_style: str  # стиль речи
    temperature: float = 0.8  # креативность
    max_tokens: int = 200  # максимальная длина ответа


class AIService:
    """
    Сервис для работы с AI.
    """

    def __init__(self, openrouter_client: OpenRouterClient):
        self.client = openrouter_client
        self.characters: Dict[str, AICharacter] = self._load_default_characters()
        self.typing_speed_range = (30, 100)  # слов в минуту (для имитации задержки)

    def _load_default_characters(self) -> Dict[str, AICharacter]:
        """
        Загружает стандартные профили персонажей.
        """
        return {
            "aggressive_mafia": AICharacter(
                name="Агрессивная мафия",
                role="mafia",
                personality="Агрессивный, подозрительный, стремится обвинять других, быстро принимает решения.",
                speaking_style="Короткие, резкие фразы. Использует сленг. Часто обвиняет.",
                temperature=0.9,
                max_tokens=100,
            ),
            "calm_civilian": AICharacter(
                name="Спокойный мирный",
                role="civilian",
                personality="Спокойный, аналитичный, старается быть логичным, ищет компромиссы.",
                speaking_style="Полные предложения, вежливый тон. Задаёт вопросы.",
                temperature=0.7,
                max_tokens=150,
            ),
            "cautious_doctor": AICharacter(
                name="Осторожный доктор",
                role="doctor",
                personality="Осторожный, эмпатичный, пытается спасти всех, склонен к паранойе.",
                speaking_style="Мягкий, заботливый. Часто использует слова 'возможно', 'я думаю'.",
                temperature=0.6,
                max_tokens=120,
            ),
            "investigative_commissioner": AICharacter(
                name="Детективный комиссар",
                role="commissioner",
                personality="Внимательный к деталям, методичный, недоверчивый, ищет улики.",
                speaking_style="Формальный, чёткий. Задаёт много уточняющих вопросов.",
                temperature=0.5,
                max_tokens=180,
            ),
        }

    def get_character(self, character_key: str) -> AICharacter:
        """
        Получить профиль персонажа по ключу.
        """
        character = self.characters.get(character_key)
        if not character:
            logger.warning(f"Персонаж {character_key} не найден, используется стандартный")
            character = AICharacter(
                name="Стандартный",
                role="civilian",
                personality="Нейтральный",
                speaking_style="Обычный",
            )
        return character

    def create_prompt(
        self,
        context: str,
        character: AICharacter,
        additional_instructions: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Создать промпт для AI на основе контекста и персонажа.
        """
        system_message = f"""Ты игрок в мафию с ролью {character.role}. Твой характер: {character.personality}
Твой стиль речи: {character.speaking_style}

Ты находишься в игровом чате. Отвечай так, как будто ты реальный игрок.
Не раскрывай свою роль явно, если это не требуется по сценарию.
Отвечай кратко и в рамках игрового процесса.

Контекст: {context}
"""
        if additional_instructions:
            system_message += f"\nДополнительные инструкции: {additional_instructions}"

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": "Что ты скажешь?"},
        ]
        return messages

    def _build_system_prompt(self, player: Any) -> str:
        """
        Построить системный промпт для игрока.

        Принимает AICharacter, экземпляр модели Player (с атрибутами ``role``,
        ``name``) или словарь с теми же ключами.
        """
        if isinstance(player, AICharacter):
            role = player.role
            name = player.name
            personality = player.personality
            speaking_style = player.speaking_style
        elif isinstance(player, dict):
            role = player.get("role", "civilian")
            name = player.get("name", "Unknown")
            personality = player.get("personality", "Нейтральный")
            speaking_style = player.get("speaking_style", "Обычный")
        else:
            # SQLAlchemy-модель или dataclass с атрибутами
            role = getattr(player, "role", "civilian")
            name = getattr(player, "name", "Unknown")
            personality = getattr(player, "personality", "Нейтральный")
            speaking_style = getattr(player, "speaking_style", "Обычный")

        return (
            f"Ты игрок в мафию с ролью {role}. Твоё имя: {name}.\n"
            f"Характер: {personality}\n"
            f"Стиль речи: {speaking_style}\n\n"
            "Ты находишься в игровом чате. Отвечай так, как будто ты реальный игрок.\n"
            "Не раскрывай свою роль явно, если это не требуется по сценарию.\n"
            "Используй доступные инструменты (tools) для выполнения игровых действий."
        )

    async def generate_response(
        self,
        context: str,
        character_key: str = "calm_civilian",
        additional_instructions: Optional[str] = None,
        simulate_typing: bool = True,
    ) -> Dict[str, Any]:
        """
        Сгенерировать ответ AI.
        Если simulate_typing=True, имитировать задержку набора текста.
        """
        character = self.get_character(character_key)
        messages = self.create_prompt(context, character, additional_instructions)

        if simulate_typing:
            # Имитируем задержку перед началом генерации (мышление)
            thinking_delay = random.uniform(0.5, 2.0)
            await asyncio.sleep(thinking_delay)

            # Имитируем набор текста: вычисляем примерное время набора на основе
            # количества слов в ожидаемом ответе (оцениваем по max_tokens)
            estimated_words = character.max_tokens // 3  # грубо
            typing_speed_wpm = random.randint(*self.typing_speed_range)
            # Время набора в секундах: слова / (слов в минуту / 60)
            typing_delay = estimated_words / (typing_speed_wpm / 60)
            # Ограничим максимальную задержку 10 секундами
            typing_delay = min(typing_delay, 10.0)
            await asyncio.sleep(typing_delay)

        # Генерация ответа через OpenRouter API
        # generate_response теперь возвращает message-объект (dict), а не полный ответ API
        ai_text = "(AI не дал ответа)"
        try:
            message = await self.client.generate_response(
                messages=messages,
                temperature=character.temperature,
                max_tokens=character.max_tokens,
                stream=False,
            )
            # message — это {"role": "assistant", "content": "...", ...}
            ai_text = message.get("content") or ai_text
        except Exception as e:
            logger.error(f"Ошибка генерации AI: {e}")
            ai_text = "Произошла ошибка. Пропускаю ход."

        return {
            "text": ai_text,
            "character": character.name,
            "role": character.role,
            "tokens_used": 0,
        }

    async def generate_structured_response(
        self,
        context: str,
        schema: Dict[str, Any],
        character_key: str = "calm_civilian",
        additional_instructions: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Сгенерировать структурированный ответ (JSON) в соответствии со схемой.
        Используется для ночных действий, голосований и т.п.
        """
        character = self.get_character(character_key)
        messages = self.create_prompt(context, character, additional_instructions)

        # Добавляем инструкцию о формате ответа
        schema_instruction = f"Ответь строго в формате JSON согласно схеме: {schema}"
        messages[-1]["content"] += f"\n{schema_instruction}"

        try:
            response = await self.client.generate_structured_response(
                messages=messages,
                schema=schema,
                temperature=character.temperature,
                max_tokens=character.max_tokens,
            )
            # Возвращаем JSON-ответ
            return response
        except Exception as e:
            logger.error(f"Ошибка структурированной генерации AI: {e}")
            return {}

    async def simulate_typing_events(
        self,
        websocket,  # WebSocket соединение игрока (если нужно отправлять события typing)
        duration: float,
        interval: float = 0.5,
    ):
        """
        Отправлять события 'typing' через WebSocket в течение указанной длительности.
        """
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < duration:
            try:
                # Отправляем событие, что AI печатает
                await websocket.send_json({"type": "ai_typing", "status": "typing"})
            except Exception as e:
                logger.warning(f"Не удалось отправить событие typing: {e}")
                break
            await asyncio.sleep(interval)
        # Отправляем событие завершения набора
        try:
            await websocket.send_json({"type": "ai_typing", "status": "finished"})
        except Exception:
            pass

    def add_character(self, key: str, character: AICharacter):
        """
        Добавить новый профиль персонажа.
        """
        self.characters[key] = character
        logger.info(f"Добавлен персонаж {key}: {character.name}")

    def list_characters(self) -> List[Dict[str, Any]]:
        """
        Получить список всех доступных персонажей.
        """
        return [
            {
                "key": key,
                "name": char.name,
                "role": char.role,
                "personality": char.personality,
            }
            for key, char in self.characters.items()
        ]


    # ------------------------------------------------------------------
    # MCP Tool-calling методы
    # ------------------------------------------------------------------

    def _build_game_context_message(self, context: dict) -> str:
        """Форматировать game_context в строку для ИИ."""
        lines: List[str] = []
        phase = context.get("phase", "unknown")
        lines.append(f"Current game phase: {phase}")

        if "night_number" in context:
            lines.append(f"Night number: {context['night_number']}")

        alive = context.get("alive_players", [])
        if alive:
            alive_names = ", ".join(
                [p.get("name", str(p.get("id", "?"))) if isinstance(p, dict) else getattr(p, "name", str(getattr(p, "id", "?"))) for p in alive]
            )
            lines.append(f"Alive players: {alive_names}")

        dead = context.get("dead_players", [])
        if dead:
            dead_names = ", ".join(
                [p.get("name", str(p.get("id", "?"))) if isinstance(p, dict) else getattr(p, "name", str(getattr(p, "id", "?"))) for p in dead]
            )
            lines.append(f"Dead players: {dead_names}")

        recent_messages = context.get("recent_messages", [])
        if recent_messages:
            lines.append("\nRecent chat messages:")
            for msg in recent_messages[-10:]:  # последние 10
                sender = msg.get("sender_name", "Unknown") if isinstance(msg, dict) else getattr(msg, "sender_name", "Unknown")
                content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
                lines.append(f"  {sender}: {content}")

        day_history = context.get("day_chat_history", [])
        if day_history:
            lines.append("\nDay discussion summary:")
            for msg in day_history[-15:]:
                sender = msg.get("sender_name", "Unknown") if isinstance(msg, dict) else getattr(msg, "sender_name", "Unknown")
                content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
                lines.append(f"  {sender}: {content}")

        if phase == "voting":
            lines.append(
                "\nYou must now vote to eliminate someone. "
                "Choose based on who seemed suspicious during discussion."
            )
        elif phase == "night":
            lines.append("\nIt is night. Perform your role action.")
        elif phase == "day":
            lines.append("\nIt is daytime. Discuss and try to find the Mafia members.")

        return "\n".join(lines)

    async def request_night_action(
        self,
        player: Any,
        game_context: dict,
        dispatcher: MCPToolDispatcher,
    ) -> dict:
        """
        Запросить у ИИ ночное действие через MCP tool calling.

        ``player`` — объект игрока (SQLAlchemy-модель, dataclass или dict)
                     с атрибутами ``id``, ``role``, ``name``.
        ``game_context`` — словарь с ключами ``alive_players``, ``dead_players``,
                           ``phase``, ``night_number``.
        """
        system_prompt = self._build_system_prompt(player)
        context_msg = self._build_game_context_message(game_context)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_msg},
        ]

        player_id = player.get("id") if isinstance(player, dict) else getattr(player, "id", 0)

        try:
            response_message = await self.client.generate_response(
                messages=messages,
                tools=NIGHT_TOOLS,
                tool_choice={"type": "function", "function": {"name": "perform_night_action"}},
            )
            results = await dispatcher.parse_and_dispatch(response_message, player_id=player_id)
            return results[0] if results else {}
        except Exception as e:
            logger.error(f"request_night_action ошибка (player_id={player_id}): {e}")
            return {"error": str(e)}

    async def request_day_message(
        self,
        player: Any,
        game_context: dict,
        dispatcher: MCPToolDispatcher,
    ) -> dict:
        """
        Запросить у ИИ сообщение для дневного чата.

        ``game_context`` — словарь с ключами ``alive_players``, ``phase``,
                           ``recent_messages``.
        """
        system_prompt = self._build_system_prompt(player)
        context_msg = self._build_game_context_message(game_context)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_msg},
        ]

        player_id = player.get("id") if isinstance(player, dict) else getattr(player, "id", 0)

        try:
            response_message = await self.client.generate_response(
                messages=messages,
                tools=DAY_TOOLS,
                tool_choice={"type": "function", "function": {"name": "send_message"}},
            )
            results = await dispatcher.parse_and_dispatch(response_message, player_id=player_id)
            return results[0] if results else {}
        except Exception as e:
            logger.error(f"request_day_message ошибка (player_id={player_id}): {e}")
            return {"error": str(e)}

    async def request_vote(
        self,
        player: Any,
        game_context: dict,
        dispatcher: MCPToolDispatcher,
    ) -> dict:
        """
        Запросить у ИИ голос за исключение игрока.

        ``game_context`` — словарь с ключами ``alive_players``,
                           ``day_chat_history``, ``phase``.
        """
        system_prompt = self._build_system_prompt(player)
        context_msg = self._build_game_context_message(game_context)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_msg},
        ]

        player_id = player.get("id") if isinstance(player, dict) else getattr(player, "id", 0)

        try:
            response_message = await self.client.generate_response(
                messages=messages,
                tools=VOTE_TOOLS,
                tool_choice={"type": "function", "function": {"name": "vote_for_player"}},
            )
            results = await dispatcher.parse_and_dispatch(response_message, player_id=player_id)
            return results[0] if results else {}
        except Exception as e:
            logger.error(f"request_vote ошибка (player_id={player_id}): {e}")
            return {"error": str(e)}


# Глобальный экземпляр сервиса для удобства
openrouter_client = OpenRouterClient()
ai_service = AIService(openrouter_client)