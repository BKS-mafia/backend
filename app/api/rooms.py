from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app import crud, schemas
from app.db.session import get_db

router = APIRouter()


@router.post("/", response_model=schemas.Room, status_code=status.HTTP_201_CREATED)
async def create_room(
    room_in: schemas.RoomCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new room.
    """
    room = await crud.room.create(db, obj_in=room_in)
    return room


@router.get("/{room_id}", response_model=schemas.Room)
async def get_room(
    room_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a room by its room_id.
    """
    room = await crud.room.get_by_room_id(db, room_id=room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@router.post("/{room_id}/join", response_model=schemas.Player)
async def join_room(
    room_id: str,
    player_in: schemas.PlayerCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Join a room as a player.
    """
    # First, get the room by room_id
    room = await crud.room.get_by_room_id(db, room_id=room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Check if the room is in lobby state
    if room.status != "lobby":
        raise HTTPException(status_code=400, detail="Room is not in lobby state")
    
    # Check if the room has space
    if room.current_players >= room.max_players:
        raise HTTPException(status_code=400, detail="Room is full")
    
    # Set the room_id for the player
    player_in.room_id = room.id
    
    # Create the player
    player = await crud.player.create(db, obj_in=player_in)
    
    # Update the room's current_players count
    room.current_players += 1
    if player_in.is_ai:
        room.ai_players += 1
    else:
        room.human_players += 1
    await db.commit()
    
    return player


@router.get("/{room_id}/players", response_model=List[schemas.Player])
async def get_room_players(
    room_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all players in a room.
    """
    room = await crud.room.get_by_room_id(db, room_id=room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    players = await crud.player.get_by_room(db, room_id=room.id)
    return players