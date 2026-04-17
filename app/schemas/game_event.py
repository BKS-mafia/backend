from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


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

    class Config:
        from_attributes = True


class GameEvent(GameEventInDBBase):
    pass