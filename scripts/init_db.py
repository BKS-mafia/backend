#!/usr/bin/env python3
"""
Script to initialize the database with tables and initial data.
"""
import asyncio
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models.base import Base
from app.models.room import Room, RoomStatus
from app.models.player import Player
from app.models.game import Game
from app.models.game_event import GameEvent
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(settings.DATABASE_URL, echo=True)

# Create async session factory
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        # Drop all tables (for development only)
        await conn.run_sync(Base.metadata.drop_all)
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created successfully")


async def create_initial_data() -> None:
    """Create initial data if needed."""
    async with async_session() as session:
        # Check if we already have data
        result = await session.execute(select(Room).limit(1))
        if result.first() is not None:
            logger.info("Database already contains data, skipping initial data creation")
            return

        # Create a sample room for testing
        sample_room = Room(
            room_id="test-room-1",
            host_token="test-host-token",
            status=RoomStatus.LOBBY,
            total_players=8,
            ai_count=3,
            people_count=5,
            current_players=0,
            ai_players=0,
            human_players=0,
            settings='{"game_mode": "classic", "time_per_phase": 30}'
        )
        session.add(sample_room)
        await session.commit()
        logger.info("Initial data created successfully")


async def main() -> None:
    """Main function to initialize database."""
    await init_db()
    await create_initial_data()


if __name__ == "__main__":
    asyncio.run(main())