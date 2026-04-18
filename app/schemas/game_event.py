from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime
import json


class GameEventBase(BaseModel):
    game_id: int
    player_id: int
    event_type: str
    event_data: Optional[Dict[str, Any]] = None


class GameEventCreate(GameEventBase):
    pass


class GameEventUpdate(BaseModel):
    event_type: Optional[str] = None
    event_data: Optional[Dict[str, Any]] = None


class GameEventInDBBase(GameEventBase):
    id: int
    created_at: datetime

    @field_validator("event_data", mode="before")
    @classmethod
    def parse_event_data(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v

    class Config:
        from_attributes = True


class GameEvent(GameEventInDBBase):
    pass
