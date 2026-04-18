from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime
import json


class RoleConfig(BaseModel):
    name: str
    count: int
    canBeHuman: bool = Field(alias="canBeHuman", default=True)
    canBeAI: bool = Field(alias="canBeAI", default=True)

    class Config:
        populate_by_name = True


class RoomBase(BaseModel):
    room_id: str
    short_id: Optional[str] = None
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

    class Config:
        populate_by_name = True


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    status: Optional[str] = None
    total_players: Optional[int] = Field(alias="totalPlayers", default=None)
    ai_count: Optional[int] = Field(alias="aiCount", default=None)
    people_count: Optional[int] = Field(alias="peopleCount", default=None)
    roles: Optional[Dict[str, RoleConfig]] = None
    current_players: Optional[int] = None
    ai_players: Optional[int] = None
    human_players: Optional[int] = None
    settings: Optional[Dict[str, Any]] = None

    class Config:
        populate_by_name = True


class RoomInDBBase(RoomBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

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

    class Config:
        from_attributes = True


class Room(RoomInDBBase):
    pass
