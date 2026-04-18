from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from datetime import datetime
import json

# Избегаем циклического импорта
if TYPE_CHECKING:
    from app.schemas.player import Player


class RoleConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    name: str
    count: int
    canBeHuman: bool = Field(alias="canBeHuman", default=True)
    canBeAI: bool = Field(alias="canBeAI", default=True)


class ChatEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    eventChat: str
    eventId: str
    type: str
    senderName: str
    body: str
    creationTime: datetime


class ChatRoom(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    name: str
    countOfUnread: int
    events: List[ChatEvent] = Field(default_factory=list)


class RoomBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    host_token: str
    status: str
    total_players: int = Field(alias="totalPlayers", default=8)
    ai_count: int = Field(alias="aiCount", default=3)
    people_count: int = Field(alias="peopleCount", default=5)
    roles: Optional[Dict[str, RoleConfig]] = None
    current_players: int = 0
    ai_players: int = 0
    human_players: int = 0
    settings: Optional[Dict[str, Any]] = None


class RoomCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    room_id: Optional[str] = Field(default=None, description="Уникальный ID комнаты. Если не передан, будет сгенерирован автоматически")
    host_token: str
    total_players: int = Field(alias="totalPlayers", default=8)
    ai_count: int = Field(alias="aiCount", default=3)
    people_count: int = Field(alias="peopleCount", default=5)
    roles: Optional[Dict[str, RoleConfig]] = None
    settings: Optional[Dict[str, Any]] = None


class RoomUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    status: Optional[str] = None
    total_players: Optional[int] = Field(alias="totalPlayers", default=None)
    ai_count: Optional[int] = Field(alias="aiCount", default=None)
    people_count: Optional[int] = Field(alias="peopleCount", default=None)
    roles: Optional[Dict[str, RoleConfig]] = None
    current_players: Optional[int] = None
    ai_players: Optional[int] = None
    human_players: Optional[int] = None
    settings: Optional[Dict[str, Any]] = None


class RoomInDBBase(RoomBase):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)
    
    id: int
    room_id: str = Field(alias="roomId")
    short_id: Optional[str] = Field(alias="shortId", default=None)
    host_token: str = Field(alias="hostToken")
    created_at: datetime = Field(alias="creationTime")
    updated_at: Optional[datetime] = Field(alias="updateTime", default=None)
    current_players: int = Field(alias="currentPlayers", default=0)
    ai_players: int = Field(alias="aiPlayers", default=0)
    human_players: int = Field(alias="humanPlayers", default=0)
    chats: List[ChatRoom] = Field(default_factory=list)

    @field_validator("roles", mode="before")
    @classmethod
    def parse_roles(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v

    @field_validator("settings", mode="before")
    @classmethod
    def parse_settings(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v

    @field_validator("chats", mode="before")
    @classmethod
    def parse_chats(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return []
        return v if v is not None else []


class Room(RoomInDBBase):
    """Схема комнаты для API ответа."""
    pass
