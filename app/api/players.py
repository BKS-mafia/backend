from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app import crud, schemas
from app.db.session import get_db

router = APIRouter()


@router.get("/{player_id}", response_model=schemas.Player)
async def get_player(
    player_id: int,
    db: AsyncSession = Depends(get_db),
) -> schemas.Player:
    """
    Получить публичный профиль игрока по его внутреннему ID.
    """
    player = await crud.player.get(db, id=player_id)
    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found",
        )
    return player
