"""
MCP (Model Context Protocol) инструменты для AI-агентов в игре Мафия.

Содержит:
- Определения инструментов в формате OpenAI/OpenRouter tool calling
- Наборы инструментов для каждой фазы игры
- MCPToolDispatcher — диспетчер вызовов инструментов
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Определения инструментов (OpenAI/OpenRouter tool calling format)
# ---------------------------------------------------------------------------

TOOL_SEND_MESSAGE = {
    "type": "function",
    "function": {
        "name": "send_message",
        "description": "Send a message to the current chat (day chat or mafia night chat).",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Message text to send",
                }
            },
            "required": ["content"],
        },
    },
}

TOOL_VOTE_FOR_PLAYER = {
    "type": "function",
    "function": {
        "name": "vote_for_player",
        "description": "Vote to eliminate a player during the voting phase.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_player_id": {
                    "type": "integer",
                    "description": "ID of the player to vote for elimination",
                }
            },
            "required": ["target_player_id"],
        },
    },
}

TOOL_PERFORM_NIGHT_ACTION = {
    "type": "function",
    "function": {
        "name": "perform_night_action",
        "description": "Perform a night action. Mafia: kill. Doctor: heal. Detective: investigate.",
        "parameters": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": ["kill", "heal", "investigate"],
                    "description": "Type of night action",
                },
                "target_player_id": {
                    "type": "integer",
                    "description": "ID of the target player",
                },
            },
            "required": ["action_type", "target_player_id"],
        },
    },
}

TOOL_GET_GAME_STATE = {
    "type": "function",
    "function": {
        "name": "get_game_state",
        "description": (
            "Get a summary of the current game state: phase, alive/dead players, recent events."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}

# ---------------------------------------------------------------------------
# Наборы инструментов для каждой фазы
# ---------------------------------------------------------------------------

DAY_TOOLS = [TOOL_SEND_MESSAGE, TOOL_GET_GAME_STATE]
VOTE_TOOLS = [TOOL_VOTE_FOR_PLAYER, TOOL_GET_GAME_STATE]
NIGHT_TOOLS = [TOOL_PERFORM_NIGHT_ACTION, TOOL_GET_GAME_STATE]


# ---------------------------------------------------------------------------
# MCPToolDispatcher
# ---------------------------------------------------------------------------


class MCPToolDispatcher:
    """
    Перехватывает tool-вызовы нейросети и делегирует их в game_service.

    Колбэки устанавливаются при создании StateMachine/GameService.
    """

    def __init__(self) -> None:
        # Колбэки: принимают player_id + аргументы, возвращают результат
        self._send_message_cb: Optional[Callable] = None
        self._vote_cb: Optional[Callable] = None
        self._night_action_cb: Optional[Callable] = None
        self._get_game_state_cb: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Регистрация колбэков
    # ------------------------------------------------------------------

    def register_send_message(self, cb: Callable) -> None:
        """Зарегистрировать колбэк для отправки сообщения."""
        self._send_message_cb = cb

    def register_vote(self, cb: Callable) -> None:
        """Зарегистрировать колбэк для голосования."""
        self._vote_cb = cb

    def register_night_action(self, cb: Callable) -> None:
        """Зарегистрировать колбэк для ночного действия."""
        self._night_action_cb = cb

    def register_get_game_state(self, cb: Callable) -> None:
        """Зарегистрировать колбэк для получения состояния игры."""
        self._get_game_state_cb = cb

    # ------------------------------------------------------------------
    # Диспатч
    # ------------------------------------------------------------------

    async def dispatch(self, tool_name: str, tool_args: dict, player_id: int) -> Any:
        """Вызвать нужный колбэк по имени инструмента."""
        if tool_name == "send_message" and self._send_message_cb:
            return await self._send_message_cb(
                player_id=player_id,
                content=tool_args.get("content", ""),
            )
        elif tool_name == "vote_for_player" and self._vote_cb:
            return await self._vote_cb(
                player_id=player_id,
                target_player_id=tool_args.get("target_player_id"),
            )
        elif tool_name == "perform_night_action" and self._night_action_cb:
            return await self._night_action_cb(
                player_id=player_id,
                action_type=tool_args.get("action_type"),
                target_player_id=tool_args.get("target_player_id"),
            )
        elif tool_name == "get_game_state" and self._get_game_state_cb:
            return await self._get_game_state_cb(player_id=player_id)

        logger.warning("MCPToolDispatcher: нет обработчика для инструмента '%s'", tool_name)
        return {"error": f"Unknown tool or no handler: {tool_name}"}

    async def parse_and_dispatch(
        self, response_message: dict, player_id: int
    ) -> list[dict]:
        """
        Парсит ответ нейросети, извлекает tool_calls и вызывает dispatch для каждого.
        Возвращает список результатов вида:
            [{"tool": str, "result": Any, "call_id": str | None}, ...]
        """
        results: list[dict] = []
        tool_calls = response_message.get("tool_calls") or []

        for call in tool_calls:
            tool_name: str = call.get("function", {}).get("name", "")
            raw_args = call.get("function", {}).get("arguments", "{}")
            try:
                tool_args: dict = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except (json.JSONDecodeError, TypeError):
                tool_args = {}

            # Логируем вызов инструмента
            logger.info(f"[MCP] Player {player_id} used tool: {tool_name} with args: {tool_args}")

            result = await self.dispatch(tool_name, tool_args, player_id)
            results.append(
                {
                    "tool": tool_name,
                    "result": result,
                    "call_id": call.get("id"),
                }
            )

        return results
