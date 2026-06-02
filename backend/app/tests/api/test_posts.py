import pytest
from httpx import AsyncClient


@pytest.mark.asyncio()
async def test_create_and_read_post(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    create_response = await client.post(
        "/api/v1/posts/",
        json={"title": "Looking for a FastAPI collaborator", "body": "Build with me", "tags": ["Python"]},
        headers=auth_headers,
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["tags"] == ["python"]

    read_response = await client.get(f"/api/v1/posts/{created['id']}")

    assert read_response.status_code == 200
    assert read_response.json()["title"] == created["title"]


@pytest.mark.asyncio()
async def test_delete_post(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    create_response = await client.post(
        "/api/v1/posts/",
        json={"title": "Delete me", "body": "Temporary", "tags": []},
        headers=auth_headers,
    )
    post_id = create_response.json()["id"]

    delete_response = await client.delete(f"/api/v1/posts/{post_id}", headers=auth_headers)
    read_response = await client.get(f"/api/v1/posts/{post_id}")

    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "ok"
    assert read_response.status_code == 404


@pytest.mark.asyncio()
async def test_feed_populates_after_follow(
    client: AsyncClient,
    auth_headers: dict[str, str],
    second_user,
    second_auth_headers: dict[str, str],
) -> None:
    post_response = await client.post(
        "/api/v1/posts/",
        json={"title": "Open source pairing", "body": "Need a TypeScript reviewer", "tags": ["TypeScript"]},
        headers=second_auth_headers,
    )
    await client.post(f"/api/v1/users/{second_user.username}/follow", headers=auth_headers)

    feed_response = await client.get("/api/v1/feed/", headers=auth_headers)

    assert post_response.status_code == 201
    assert feed_response.status_code == 200
    assert feed_response.json()[0]["id"] == post_response.json()["id"]


@pytest.mark.asyncio()
async def test_cannot_delete_another_users_post(
    client: AsyncClient,
    auth_headers: dict[str, str],
    second_auth_headers: dict[str, str],
) -> None:
    create_response = await client.post(
        "/api/v1/posts/",
        json={"title": "Mine", "body": "Only I can delete", "tags": []},
        headers=second_auth_headers,
    )

    response = await client.delete(f"/api/v1/posts/{create_response.json()['id']}", headers=auth_headers)

    assert response.status_code == 403
