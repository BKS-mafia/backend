from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
import enum
import json


class GamePhase(str, enum.Enum):
    LOBBY = "lobby"
    NIGHT = "night"
    DAY = "day"
    VOTING = "voting"
    FINISHED = "finished"
    TURING_TEST = "turing_test"


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
    turing_votes: Optional[Dict[str, Any]] = None
    humanness_scores: Optional[Dict[str, Any]] = None


class GameInDBBase(GameBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    turing_votes: Optional[Dict[str, Any]] = None
    # Пример: {"player_id_1": [voter_id_1, voter_id_2], ...}
    humanness_scores: Optional[Dict[str, Any]] = None
    # Пример: {"player_id_1": 0.75, "player_id_2": 0.33, ...}

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


# Алиас для явного использования как response-схемы
GameResponse = Game
