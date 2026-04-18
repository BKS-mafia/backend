from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime
import json


class RoomBase(BaseModel):
    room_id: str
    host_token: str
    status: str
    max_players: int = 10
    min_players: int = 5
    current_players: int = 0
    ai_players: int = 0
    human_players: int = 0
    settings: Optional[Dict[str, Any]] = None


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    status: Optional[str] = None
    max_players: Optional[int] = None
    min_players: Optional[int] = None
    current_players: Optional[int] = None
    ai_players: Optional[int] = None
    human_players: Optional[int] = None
    settings: Optional[Dict[str, Any]] = None


class RoomInDBBase(RoomBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

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
