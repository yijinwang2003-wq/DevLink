import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.models.chat import ChatMessage, ChatRoom
from app.models.user import User
from app.services.user_service import get_user_by_id, get_user_by_username

HEARTBEAT_INTERVAL_SECONDS = 30
MAX_CHAT_MESSAGE_CHARS = 2000


class ConnectionManager:
    def __init__(self) -> None:
        self.active: dict[str, list[WebSocket]] = {}
        self.heartbeat_tasks: dict[WebSocket, asyncio.Task[None]] = {}

    async def connect(self, websocket: WebSocket, room_id: UUID) -> None:
        await websocket.accept()
        self.active.setdefault(str(room_id), []).append(websocket)
        self.heartbeat_tasks[websocket] = asyncio.create_task(
            self._heartbeat(websocket, room_id)
        )

    def disconnect(self, websocket: WebSocket, room_id: UUID) -> None:
        room_key = str(room_id)
        connections = self.active.get(room_key, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections and room_key in self.active:
            del self.active[room_key]

        heartbeat_task = self.heartbeat_tasks.pop(websocket, None)
        if heartbeat_task is not None and heartbeat_task is not asyncio.current_task():
            heartbeat_task.cancel()

    async def broadcast(self, message: dict[str, str], room_id: UUID) -> None:
        disconnected: list[WebSocket] = []
        for websocket in self.active.get(str(room_id), []):
            try:
                await websocket.send_json(message)
            except RuntimeError:
                disconnected.append(websocket)
        for websocket in disconnected:
            self.disconnect(websocket, room_id)

    async def _heartbeat(self, websocket: WebSocket, room_id: UUID) -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                await websocket.send_json({"type": "ping"})
        except (RuntimeError, WebSocketDisconnect):
            self.disconnect(websocket, room_id)
        except asyncio.CancelledError:
            raise


manager = ConnectionManager()


def ordered_dm_pair(first_user_id: UUID, second_user_id: UUID) -> tuple[UUID, UUID]:
    return (
        (first_user_id, second_user_id)
        if str(first_user_id) < str(second_user_id)
        else (second_user_id, first_user_id)
    )


def room_has_user(room: ChatRoom, user_id: UUID) -> bool:
    return user_id in {room.user_low_id, room.user_high_id}


def extract_message_content(payload: object) -> str | None:
    if not isinstance(payload, dict):
        raise ValueError("Invalid message payload")

    if payload.get("type") == "pong":
        return None

    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Invalid message content")

    content = content.strip()
    if len(content) > MAX_CHAT_MESSAGE_CHARS:
        raise ValueError("Message is too large")

    return content


async def create_or_get_dm_room(
    db: AsyncSession,
    current_user: User,
    recipient_username: str,
) -> ChatRoom:
    recipient = await get_user_by_username(db, recipient_username)
    if recipient is None or not recipient.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    if recipient.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create a room with yourself",
        )

    user_low_id, user_high_id = ordered_dm_pair(current_user.id, recipient.id)
    result = await db.execute(
        select(ChatRoom).where(
            ChatRoom.user_low_id == user_low_id,
            ChatRoom.user_high_id == user_high_id,
        )
    )
    room = result.scalar_one_or_none()
    if room is not None:
        return room

    room = ChatRoom(user_low_id=user_low_id, user_high_id=user_high_id)
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


async def list_rooms_for_user(db: AsyncSession, user: User) -> list[ChatRoom]:
    result = await db.execute(
        select(ChatRoom)
        .where(or_(ChatRoom.user_low_id == user.id, ChatRoom.user_high_id == user.id))
        .order_by(ChatRoom.updated_at.desc())
    )
    return list(result.scalars().all())


async def list_room_messages(
    db: AsyncSession,
    room_id: UUID,
    current_user: User,
    page: int = 1,
    size: int = 50,
) -> list[ChatMessage]:
    room = await get_room_for_user(db, room_id, current_user)
    offset = (page - 1) * size
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.room_id == room.id)
        .order_by(ChatMessage.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    return list(result.scalars().all())


async def get_room_for_user(db: AsyncSession, room_id: UUID, user: User) -> ChatRoom:
    room = await db.get(ChatRoom, room_id)
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
        )
    if not room_has_user(room, user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Room access denied"
        )
    return room


async def persist_message(
    db: AsyncSession,
    room_id: UUID,
    sender: User,
    content: str,
) -> ChatMessage:
    room = await get_room_for_user(db, room_id, sender)
    room.updated_at = datetime.now(timezone.utc)
    message = ChatMessage(room_id=room.id, sender_id=sender.id, content=content)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def authenticate_websocket_user(db: AsyncSession, token: str | None) -> User:
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Missing token"
        )
    payload = decode_token(token)
    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token"
        )

    try:
        user_id = UUID(subject)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token"
        ) from exc

    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found or inactive",
        )
    return user


async def handle_websocket_chat(
    websocket: WebSocket,
    db: AsyncSession,
    room_id: UUID,
    token: str | None,
) -> None:
    try:
        current_user = await authenticate_websocket_user(db, token)
        await get_room_for_user(db, room_id, current_user)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket, room_id)
    try:
        while True:
            payload = await websocket.receive_json()
            try:
                content = extract_message_content(payload)
            except ValueError:
                await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
                return
            if content is None:
                continue

            message = await persist_message(db, room_id, current_user, content)
            await manager.broadcast(
                {
                    "type": message.message_type,
                    "content": message.content,
                    "sender_id": str(message.sender_id),
                    "timestamp": message.created_at.isoformat(),
                },
                room_id,
            )
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, room_id)
