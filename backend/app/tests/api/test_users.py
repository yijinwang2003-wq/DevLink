import pytest
from httpx import AsyncClient


@pytest.mark.asyncio()
async def test_get_users_me(
    client: AsyncClient,
    test_user,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get("/api/v1/users/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["username"] == test_user.username


@pytest.mark.asyncio()
async def test_update_users_me_partial_update(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.put(
        "/api/v1/users/me",
        json={
            "bio": "Backend engineer",
            "github_url": "https://github.com/alice",
            "skills": ["python", "fastapi"],
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["bio"] == "Backend engineer"
    assert response.json()["skills"] == ["python", "fastapi"]


@pytest.mark.asyncio()
async def test_get_user_by_username(client: AsyncClient, test_user) -> None:
    response = await client.get(f"/api/v1/users/{test_user.username}")

    assert response.status_code == 200
    assert response.json()["id"] == str(test_user.id)


@pytest.mark.asyncio()
async def test_list_users_by_skill_with_pagination(
    client: AsyncClient,
    auth_headers: dict[str, str],
    second_user,
    second_auth_headers: dict[str, str],
) -> None:
    await client.put(
        "/api/v1/users/me",
        json={"skills": ["python", "fastapi"]},
        headers=auth_headers,
    )
    await client.put(
        "/api/v1/users/me",
        json={"skills": ["typescript"]},
        headers=second_auth_headers,
    )

    response = await client.get("/api/v1/users/?skill=python&page=1&size=20")

    assert response.status_code == 200
    users = response.json()
    assert len(users) == 1
    assert users[0]["username"] == "alice"
