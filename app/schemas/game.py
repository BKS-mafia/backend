from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


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

    class Config:
        orm_mode = True


class Game(GameInDBBase):
    pass