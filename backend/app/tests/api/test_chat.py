import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user import UserCreate
from app.services.chat_service import (
    create_or_get_dm_room,
    get_room_for_user,
    list_room_messages,
    persist_message,
)
from app.services.user_service import create_user


@pytest.mark.asyncio()
async def test_create_and_get_dm_room(
    client: AsyncClient,
    auth_headers: dict[str, str],
    second_user,
) -> None:
    create_response = await client.post(
        "/api/v1/chat/rooms/",
        json={"recipient_username": second_user.username},
        headers=auth_headers,
    )
    duplicate_response = await client.post(
        "/api/v1/chat/rooms/",
        json={"recipient_username": second_user.username},
        headers=auth_headers,
    )
    list_response = await client.get("/api/v1/chat/rooms/", headers=auth_headers)

    assert create_response.status_code == 201
    assert duplicate_response.status_code == 201
    assert duplicate_response.json()["id"] == create_response.json()["id"]
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == create_response.json()["id"]


@pytest.mark.asyncio()
async def test_unauthorized_room_access(
    db: AsyncSession,
    test_user,
    second_user,
) -> None:
    third_user = await create_user(
        db,
        UserCreate(email="cara@example.com", username="cara", password="password123"),
    )
    room = await create_or_get_dm_room(db, test_user, second_user.username)

    with pytest.raises(HTTPException) as exc_info:
        await get_room_for_user(db, room.id, third_user)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio()
async def test_message_persistence_service(
    db: AsyncSession,
    test_user,
    second_user,
) -> None:
    room = await create_or_get_dm_room(db, test_user, second_user.username)
    previous_updated_at = room.updated_at

    message = await persist_message(db, room.id, test_user, "hello")
    await db.refresh(room)

    assert message.room_id == room.id
    assert message.sender_id == test_user.id
    assert message.content == "hello"
    assert message.message_type == "message"
    assert room.updated_at > previous_updated_at


@pytest.mark.asyncio()
async def test_list_room_messages_newest_first(
    db: AsyncSession,
    test_user,
    second_user,
) -> None:
    room = await create_or_get_dm_room(db, test_user, second_user.username)
    first_message = await persist_message(db, room.id, test_user, "first")
    second_message = await persist_message(db, room.id, second_user, "second")

    messages = await list_room_messages(db, room.id, test_user, page=1, size=50)

    assert [message.id for message in messages] == [second_message.id, first_message.id]


@pytest.mark.asyncio()
async def test_get_room_messages_endpoint(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    test_user,
    second_user,
) -> None:
    room = await create_or_get_dm_room(db, test_user, second_user.username)
    await persist_message(db, room.id, test_user, "hello")

    response = await client.get(
        f"/api/v1/chat/rooms/{room.id}/messages?page=1&size=50",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()[0]["content"] == "hello"
    assert "room_id" not in response.json()[0]
