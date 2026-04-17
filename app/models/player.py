from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base
import enum


class PlayerRole(str, enum.Enum):
    MAFIA = "mafia"
    DOCTOR = "doctor"
    COMMISSIONER = "commissioner"
    CIVILIAN = "civilian"


class PlayerType(str, enum.Enum):
    HUMAN = "human"
    AI = "ai"


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(String, unique=True, index=True, nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    nickname = Column(String, nullable=False)
    is_ai = Column(Boolean, default=False)
    role = Column(Enum(PlayerRole), nullable=True)
    is_alive = Column(Boolean, default=True)
    is_connected = Column(Boolean, default=True)
    session_token = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    room = relationship("Room", back_populates="players")
    game_events = relationship("GameEvent", back_populates="player", cascade="all, delete-orphan")