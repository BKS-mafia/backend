from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime
import json


class GameBase(BaseModel):
    room_id: int
    status: str
    day_number: int = 1
    night_actions: Optional[Dict[str, Any]] = None
    voting_results: Optional[Dict[str, Any]] = None
    winner: Optional[str] = None


class GameCreate(GameBase):
    pass


class GameUpdate(BaseModel):
    status: Optional[str] = None
    day_number: Optional[int] = None
    night_actions: Optional[Dict[str, Any]] = None
    voting_results: Optional[Dict[str, Any]] = None
    winner: Optional[str] = None


class GameInDBBase(GameBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator("night_actions", mode="before")
    @classmethod
    def parse_night_actions(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v

    @field_validator("voting_results", mode="before")
    @classmethod
    def parse_voting_results(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v

    class Config:
        from_attributes = True


class Game(GameInDBBase):
    pass
