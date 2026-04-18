from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base
import enum


class RoomStatus(str, enum.Enum):
    LOBBY = "lobby"
    STARTING = "starting"
    PLAYING = "playing"
    FINISHED = "finished"


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, unique=True, index=True, nullable=False)
    short_id = Column(String, unique=True, index=True, nullable=True, default=None)
    host_token = Column(String, unique=True, nullable=False)
    status = Column(Enum(RoomStatus), default=RoomStatus.LOBBY)
    total_players = Column(Integer, default=8)
    ai_count = Column(Integer, default=3)
    people_count = Column(Integer, default=5)
    roles = Column(Text)  # JSON string with roles configuration
    chats = Column(Text, default="[]")  # JSON string with list of chats
    current_players = Column(Integer, default=0)
    ai_players = Column(Integer, default=0)
    human_players = Column(Integer, default=0)
    settings = Column(Text)  # JSON string with game settings
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    players = relationship("Player", back_populates="room", cascade="all, delete-orphan")
    games = relationship("Game", back_populates="room", cascade="all, delete-orphan")
