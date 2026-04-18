from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from typing import List, Any, Dict, Optional

from app import crud, schemas
from app.db.session import get_db
from app.services.room_service import room_service
from app.services.game_service import game_service

router = APIRouter()


async def resolve_room_id(room_id_or_short: str, db: AsyncSession) -> Optional[str]:
    """
    Преобразует room_id или short_id в room_id (UUID).
    Если передан UUID - возвращает его напрямую.
    Если передан short_id - ищет комнату и возвращает её room_id.
    """
    # Проверяем, является ли это short_id (5 символов, буквы и цифры)
    if len(room_id_or_short) == 5 and room_id_or_short.isalnum():
        room = await room_service.get_room_by_short_id(db, short_id=room_id_or_short)
        if room:
            return room.room_id
    
    # Иначе считаем, что это room_id (UUID)
    room = await room_service.get_room_by_public_id(db, public_room_id=room_id_or_short)
    if room:
        return room.room_id
    
    return None


# ── GET /s/{short_id} — редирект на комнату по short_id ────────────────────────

@router.get("/s/{short_id}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def redirect_short_id(
    short_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Перенаправить на страницу комнаты по short_id.
    """
    room = await room_service.get_room_by_short_id(db, short_id=short_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    return RedirectResponse(url=f"/api/rooms/{room.room_id}")


# ── 2.1 GET / — список активных лобби ────────────────────────────────────────

@router.get("/", response_model=List[schemas.Room])
async def list_rooms(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> List[schemas.Room]:
    """
    Получить список активных лобби для браузера комнат.
    Возвращает только комнаты со статусом 'lobby' или 'starting'.
    """
    rooms = await crud.room.get_active(db, skip=skip, limit=limit)
    return rooms


# ── Существующий POST / — создать комнату ────────────────────────────────────

@router.post("/", response_model=schemas.Room, status_code=status.HTTP_201_CREATED)
async def create_room(
    room_in: schemas.RoomCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.Room:
    """
    Создать новую комнату.
    """
    try:
        room = await room_service.create_room(db, room_create=room_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except IntegrityError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Room with such parameters already exists")
    return room


# ── GET /{room_id} — получить комнату ────────────────────────────────────────

@router.get("/{room_id}")
async def get_room(
    room_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Получить комнату по её публичному room_id (UUID) или short_id.
    Возвращает полную информацию о комнате, включая игроков и чаты.
    """
    # Пробуем найти по short_id, если это 5-символьный код
    if len(room_id) == 5 and room_id.isalnum():
        room = await room_service.get_room_by_short_id(db, short_id=room_id)
    else:
        room = await room_service.get_room_by_public_id(db, public_room_id=room_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    
    # Получаем игроков комнаты
    players = await crud.player.get_by_room(db, room_id=room.id)
    
    # Преобразуем комнату в словарь
    room_data = schemas.Room.model_validate(room).model_dump(by_alias=True)
    
    # Добавляем игроков как Players
    room_data["Players"] = [schemas.Player.model_validate(p).model_dump(by_alias=True) for p in players]
    
    return room_data


# ── 2.2 PATCH /{room_id} — обновить настройки комнаты ───────────────────────

@router.patch("/{room_id}", response_model=schemas.Room)
async def update_room(
    room_id: str,
    room_update: schemas.RoomUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.Room:
    """
    Обновить настройки комнаты.
    Только хост может менять настройки (проверка host_token через заголовок при необходимости).
    Принимает как room_id (UUID), так и short_id.
    """
    # Пробуем найти по short_id, если это 5-символьный код
    if len(room_id) == 5 and room_id.isalnum():
        room = await room_service.get_room_by_short_id(db, short_id=room_id)
    else:
        room = await room_service.get_room_by_public_id(db, public_room_id=room_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    try:
        updated = await room_service.update_room(db, room_id=room.id, room_update=room_update)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return updated


# ── 2.3 DELETE /{room_id} — удалить комнату ──────────────────────────────────

@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Удалить комнату и уведомить подключённых игроков.
    Принимает как room_id (UUID), так и short_id.
    """
    # Пробуем найти по short_id, если это 5-символьный код
    if len(room_id) == 5 and room_id.isalnum():
        room = await room_service.get_room_by_short_id(db, short_id=room_id)
    else:
        room = await room_service.get_room_by_public_id(db, public_room_id=room_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    await room_service.delete_room(db, room_id=room.id)


# ── POST /{room_id}/join — присоединиться к комнате ─────────────────────────

@router.post("/{room_id}/join", response_model=schemas.Player)
async def join_room(
    room_id: str,
    player_in: schemas.PlayerCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.Player:
    """
    Присоединиться к комнате как игрок.
    Принимает как room_id (UUID), так и short_id.
    """
    # Пробуем найти по short_id, если это 5-символьный код
    if len(room_id) == 5 and room_id.isalnum():
        room = await room_service.get_room_by_short_id(db, short_id=room_id)
    else:
        room = await room_service.get_room_by_public_id(db, public_room_id=room_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    # Устанавливаем внутренний DB-идентификатор комнаты для игрока
    player_in = player_in.model_copy(update={"room_id": room.id})

    try:
        player = await room_service.join_player(
            db, room_id=room.id, player_create=player_in
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return player


# ── GET /{room_id}/players — список игроков в комнате ───────────────────────

@router.get("/{room_id}/players", response_model=List[schemas.Player])
async def get_room_players(
    room_id: str,
    db: AsyncSession = Depends(get_db),
) -> List[schemas.Player]:
    """
    Получить всех игроков в комнате.
    Принимает как room_id (UUID), так и short_id.
    """
    # Пробуем найти по short_id, если это 5-символьный код
    if len(room_id) == 5 and room_id.isalnum():
        room = await room_service.get_room_by_short_id(db, short_id=room_id)
    else:
        room = await room_service.get_room_by_public_id(db, public_room_id=room_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    players = await crud.player.get_by_room(db, room_id=room.id)
    return players


# ── 2.4 GET /{room_id}/game — получить игровую сессию ───────────────────────

@router.get("/{room_id}/game", response_model=schemas.Game)
async def get_room_game(
    room_id: str,
    db: AsyncSession = Depends(get_db),
) -> schemas.Game:
    """
    Получить текущую игровую сессию для комнаты.
    Принимает как room_id (UUID), так и short_id.
    """
    # Пробуем найти по short_id, если это 5-символьный код
    if len(room_id) == 5 and room_id.isalnum():
        room = await room_service.get_room_by_short_id(db, short_id=room_id)
    else:
        room = await room_service.get_room_by_public_id(db, public_room_id=room_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    game = await crud.game.get_by_room(db, room_id=room.id)
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active game found for this room",
        )
    return game


# ── 2.5 GET /{room_id}/game/state — текущее состояние игры ──────────────────

@router.get("/{room_id}/game/state")
async def get_game_state(
    room_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Получить текущую фазу игры, номер дня, список живых игроков.
    Принимает как room_id (UUID), так и short_id.
    """
    # Пробуем найти по short_id, если это 5-символьный код
    if len(room_id) == 5 and room_id.isalnum():
        room = await room_service.get_room_by_short_id(db, short_id=room_id)
    else:
        room = await room_service.get_room_by_public_id(db, public_room_id=room_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    game = await crud.game.get_by_room(db, room_id=room.id)
    machine = game_service.active_machines.get(room.id)
    players = await crud.player.get_by_room(db, room_id=room.id)

    alive_players = [
        {
            "id": p.id,
            "nickname": p.nickname,
            "is_ai": p.is_ai,
            "is_connected": p.is_connected,
        }
        for p in players
        if p.is_alive
    ]

    return {
        "room_id": room_id,
        "status": game.status if game else room.status,
        "phase": machine.current_phase.value if machine and machine.current_phase else None,
        "day_number": machine.day_number if machine else (game.day_number if game else None),
        "alive_players": alive_players,
        "total_players": len(players),
        "alive_count": len(alive_players),
    }


# ── 2.6 POST /{room_id}/game/start — HTTP-старт игры ────────────────────────

@router.post("/{room_id}/game/start")
async def start_game(
    room_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    HTTP-альтернатива WebSocket start_game событию.
    Запускает игру в комнате.
    Принимает как room_id (UUID), так и short_id.
    """
    # Пробуем найти по short_id, если это 5-символьный код
    if len(room_id) == 5 and room_id.isalnum():
        room = await room_service.get_room_by_short_id(db, short_id=room_id)
    else:
        room = await room_service.get_room_by_public_id(db, public_room_id=room_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    try:
        result = await game_service.start_game_for_room(db, room_id=room.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {
        "room_id": room_id,
        "game_id": result.get("game_id"),
        "message": result.get("message", "Game started"),
    }


# ── 2.7 GET /{room_id}/game/events — история событий ────────────────────────

@router.get("/{room_id}/game/events", response_model=List[schemas.GameEvent])
async def get_game_events(
    room_id: str,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> List[schemas.GameEvent]:
    """
    Получить историю событий текущей игры в комнате.
    Принимает как room_id (UUID), так и short_id.
    """
    # Пробуем найти по short_id, если это 5-символьный код
    if len(room_id) == 5 and room_id.isalnum():
        room = await room_service.get_room_by_short_id(db, short_id=room_id)
    else:
        room = await room_service.get_room_by_public_id(db, public_room_id=room_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    game = await crud.game.get_by_room(db, room_id=room.id)
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active game found for this room",
        )

    events = await crud.game_event.get_by_game(
        db, game_id=game.id, skip=skip, limit=limit
    )
    return events


# ── GET /{room_id}/chats — получить историю чатов комнаты ───────────────────

@router.get("/{room_id}/chats", response_model=List[schemas.ChatRoom])
async def get_room_chats(
    room_id: str,
    db: AsyncSession = Depends(get_db),
) -> List[schemas.ChatRoom]:
    """
    Получить историю чатов для комнаты.
    Принимает как room_id (UUID), так и short_id.
    Возвращает список чатов с событиями.
    """
    # Пробуем найти по short_id, если это 5-символьный код
    if len(room_id) == 5 and room_id.isalnum():
        room = await room_service.get_room_by_short_id(db, short_id=room_id)
    else:
        room = await room_service.get_room_by_public_id(db, public_room_id=room_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    chats_data = await crud.room.get_chats(db, room_id=room.room_id)
    if chats_data is None:
        return []
    
    # Преобразуем dict в ChatRoom объекты
    return [schemas.ChatRoom(**chat) for chat in chats_data]


# ── 2.8 DELETE /{room_id}/players/{player_id} — кик игрока ──────────────────

@router.delete("/{room_id}/players/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def kick_player(
    room_id: str,
    player_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Удалить игрока из комнаты (кик через HTTP).
    Принимает как room_id (UUID), так и short_id.
    """
    # Пробуем найти по short_id, если это 5-символьный код
    if len(room_id) == 5 and room_id.isalnum():
        room = await room_service.get_room_by_short_id(db, short_id=room_id)
    else:
        room = await room_service.get_room_by_public_id(db, public_room_id=room_id)
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    target_player = await crud.player.get(db, id=player_id)
    if not target_player or target_player.room_id != room.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found in this room",
        )

    # Уведомить игрока через WebSocket о кике (если подключён)
    from app.websocket.manager import manager
    await manager.send_to_player(
        player_id,
        {"type": "kicked", "message": "You have been removed from the room."},
    )
    await manager.disconnect_player(player_id)

    # Удалить из БД и обновить счётчики
    await crud.player.delete(db, id=player_id)

    new_count = max(0, room.current_players - 1)
    human_delta = 0 if target_player.is_ai else 1
    ai_delta = 1 if target_player.is_ai else 0
    await crud.room.update(
        db,
        db_obj=room,
        obj_in=schemas.RoomUpdate(
            current_players=new_count,
            human_players=max(0, room.human_players - human_delta),
            ai_players=max(0, room.ai_players - ai_delta),
        ),
    )

    # Уведомить комнату
    await manager.broadcast_to_room(
        room.id,
        {
            "type": "player_kicked",
            "player_id": player_id,
            "nickname": target_player.nickname,
        },
    )
