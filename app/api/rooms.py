from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app import crud, schemas
from app.db.session import get_db
from app.services.room_service import room_service

router = APIRouter()


@router.post("/", response_model=schemas.Room, status_code=status.HTTP_201_CREATED)
async def create_room(
    room_in: schemas.RoomCreate,
    db: AsyncSession = Depends(get_db)
) -> schemas.Room:
    """
    Create a new room.
    """
    try:
        room = await room_service.create_room(db, room_create=room_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return room


@router.get("/{room_id}", response_model=schemas.Room)
async def get_room(
    room_id: str,
    db: AsyncSession = Depends(get_db)
) -> schemas.Room:
    """
    Get a room by its room_id.
    """
    room = await room_service.get_room_by_public_id(db, public_room_id=room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    return room


@router.post("/{room_id}/join", response_model=schemas.Player)
async def join_room(
    room_id: str,
    player_in: schemas.PlayerCreate,
    db: AsyncSession = Depends(get_db)
) -> schemas.Player:
    """
    Join a room as a player.
    """
    # Получаем комнату по публичному room_id (UUID-строка)
    room = await room_service.get_room_by_public_id(db, public_room_id=room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    # Устанавливаем внутренний DB-идентификатор комнаты для игрока (Pydantic v2)
    player_in = player_in.model_copy(update={"room_id": room.id})

    try:
        player = await room_service.join_player(
            db, room_id=room.id, player_create=player_in
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return player


@router.get("/{room_id}/players", response_model=List[schemas.Player])
async def get_room_players(
    room_id: str,
    db: AsyncSession = Depends(get_db)
) -> List[schemas.Player]:
    """
    Get all players in a room.
    """
    room = await room_service.get_room_by_public_id(db, public_room_id=room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    players = await crud.player.get_by_room(db, room_id=room.id)
    return players