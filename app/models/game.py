from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Text
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


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    status = Column(Enum(GameStatus), default=GameStatus.LOBBY)
    day_number = Column(Integer, default=1)
    night_actions = Column(Text)  # JSON string of night actions
    voting_results = Column(Text)  # JSON string of voting results
    winner = Column(String, nullable=True)  # e.g., "mafia", "civilians"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    room = relationship("Room", back_populates="games")
    events = relationship("GameEvent", back_populates="game", cascade="all, delete-orphan")