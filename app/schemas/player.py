from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


class PlayerBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    player_id: str = Field(alias="playerId")
    room_id: Optional[int] = Field(alias="roomId", default=None)
    nickname: str
    is_ai: bool = Field(alias="isAI", default=False)
    role: Optional[str] = None
    is_alive: bool = Field(alias="isAlive", default=True)
    is_connected: bool = Field(alias="isConnected", default=True)
    session_token: Optional[str] = Field(alias="sessionToken", default=None)


class PlayerCreate(PlayerBase):
    pass


class PlayerUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    nickname: Optional[str] = None
    is_ai: Optional[bool] = Field(alias="isAI", default=None)
    role: Optional[str] = None
    is_alive: Optional[bool] = Field(alias="isAlive", default=None)
    is_connected: Optional[bool] = Field(alias="isConnected", default=None)
    session_token: Optional[str] = Field(alias="sessionToken", default=None)


class PlayerInDBBase(PlayerBase):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)
    
    id: int
    created_at: datetime = Field(alias="creationTime")
    updated_at: Optional[datetime] = Field(alias="updateTime", default=None)


class Player(PlayerInDBBase):
    pass