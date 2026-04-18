from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base
import enum


class GameStatus(str, enum.Enum):
    LOBBY = "lobby"
    NIGHT = "night"
    DAY = "day"
    VOTING = "voting"
    FINISHED = "finished"
    TURING_TEST = "turing_test"


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    status = Column(Enum(GameStatus), default=GameStatus.LOBBY)
    day_number = Column(Integer, default=1)
    night_actions = Column(Text)  # JSON string of night actions
    voting_results = Column(Text)  # JSON string of voting results
    winner = Column(String, nullable=True)  # e.g., "mafia", "civilians"
    turing_votes = Column(JSON, nullable=True, default=None)
    # Пример: {"player_id_1": [voter_id_1, voter_id_2], ...}
    humanness_scores = Column(JSON, nullable=True, default=None)
    # Пример: {"player_id_1": 0.75, "player_id_2": 0.33, ...}
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    room = relationship("Room", back_populates="games")
    events = relationship("GameEvent", back_populates="game", cascade="all, delete-orphan")