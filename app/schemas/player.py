from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PlayerBase(BaseModel):
    player_id: str
    room_id: int
    nickname: str
    is_ai: bool = False
    role: Optional[str] = None
    is_alive: bool = True
    is_connected: bool = True
    session_token: Optional[str] = None


class PlayerCreate(PlayerBase):
    pass


class PlayerUpdate(BaseModel):
    nickname: Optional[str] = None
    is_ai: Optional[bool] = None
    role: Optional[str] = None
    is_alive: Optional[bool] = None
    is_connected: Optional[bool] = None
    session_token: Optional[str] = None


class PlayerInDBBase(PlayerBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class Player(PlayerInDBBase):
    pass