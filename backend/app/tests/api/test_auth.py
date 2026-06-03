import pytest
from httpx import AsyncClient

from app.core.rate_limit import limiter


@pytest.mark.asyncio()
async def test_register_creates_user(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "dev@example.com", "username": "dev", "password": "password123"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "dev@example.com"
    assert body["username"] == "dev"
    assert "hashed_password" not in body


@pytest.mark.asyncio()
async def test_duplicate_email_returns_409(client: AsyncClient) -> None:
    payload = {"email": "dev@example.com", "username": "dev", "password": "password123"}
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201

    response = await client.post(
        "/api/v1/auth/register",
        json={**payload, "username": "other"},
    )

    assert response.status_code == 409


@pytest.mark.asyncio()
async def test_login_returns_access_token_and_refresh_cookie(
    client: AsyncClient, test_user
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user.email, "password": "password123"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"
    assert "refresh_token" in response.cookies


@pytest.mark.asyncio()
async def test_login_wrong_password_returns_401(client: AsyncClient, test_user) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user.email, "password": "wrong-password"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio()
async def test_me_requires_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")

    assert response.status_code == 401


@pytest.mark.asyncio()
async def test_me_with_token_returns_current_user(
    client: AsyncClient,
    test_user,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get("/api/v1/users/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(test_user.id)
    assert response.json()["email"] == test_user.email


@pytest.mark.asyncio()
async def test_refresh_token_returns_new_access_token(
    client: AsyncClient, test_user
) -> None:
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user.email, "password": "password123"},
    )

    response = await client.post("/api/v1/auth/refresh", cookies=login_response.cookies)

    assert response.status_code == 200
    assert response.json()["access_token"]


@pytest.mark.asyncio()
async def test_logout_clears_refresh_cookie(client: AsyncClient, test_user) -> None:
    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": test_user.email, "password": "password123"},
    )

    response = await client.post("/api/v1/auth/logout", cookies=login_response.cookies)

    assert response.status_code == 200
    assert response.cookies.get("refresh_token") is None


@pytest.mark.asyncio()
async def test_register_rate_limit_returns_json_429(client: AsyncClient) -> None:
    previous_enabled = limiter.enabled
    limiter.enabled = True
    limiter.reset()
    try:
        last_response = None
        for index in range(6):
            last_response = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"rate{index}@example.com",
                    "username": f"rate{index}",
                    "password": "password123",
                },
            )

        assert last_response is not None
        assert last_response.status_code == 429
        assert last_response.json() == {"detail": "Rate limit exceeded"}
    finally:
        limiter.reset()
        limiter.enabled = previous_enabled
