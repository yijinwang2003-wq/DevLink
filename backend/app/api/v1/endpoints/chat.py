from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import AsyncSessionLocal, get_db
from app.models.user import User
from app.schemas.chat import ChatMessageHistoryRead, ChatRoomCreate, ChatRoomRead
from app.services.chat_service import (
    create_or_get_dm_room,
    handle_websocket_chat,
    list_room_messages,
    list_rooms_for_user,
)

router = APIRouter()
websocket_router = APIRouter()


@router.get("/rooms/", response_model=list[ChatRoomRead])
async def rooms(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChatRoomRead]:
    return await list_rooms_for_user(db, current_user)


@router.post(
    "/rooms/", response_model=ChatRoomRead, status_code=status.HTTP_201_CREATED
)
async def create_room(
    room_create: ChatRoomCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatRoomRead:
    return await create_or_get_dm_room(db, current_user, room_create.recipient_username)


@router.get("/rooms/{room_id}/messages", response_model=list[ChatMessageHistoryRead])
async def room_messages(
    room_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChatMessageHistoryRead]:
    return await list_room_messages(db, room_id, current_user, page=page, size=size)


@websocket_router.websocket("/ws/chat/{room_id}")
async def websocket_chat(
    websocket: WebSocket, room_id: UUID, token: str | None = None
) -> None:
    async with AsyncSessionLocal() as db:
        await handle_websocket_chat(websocket, db, room_id, token)
