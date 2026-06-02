import pytest
from httpx import AsyncClient


@pytest.mark.asyncio()
async def test_follow_user(
    client: AsyncClient,
    auth_headers: dict[str, str],
    second_user,
) -> None:
    response = await client.post(
        f"/api/v1/users/{second_user.username}/follow", headers=auth_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["following_id"] == str(second_user.id)


@pytest.mark.asyncio()
async def test_unfollow_user(
    client: AsyncClient,
    auth_headers: dict[str, str],
    second_user,
) -> None:
    await client.post(
        f"/api/v1/users/{second_user.username}/follow", headers=auth_headers
    )

    response = await client.delete(
        f"/api/v1/users/{second_user.username}/follow", headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio()
async def test_list_followers_and_following(
    client: AsyncClient,
    test_user,
    auth_headers: dict[str, str],
    second_user,
) -> None:
    await client.post(
        f"/api/v1/users/{second_user.username}/follow", headers=auth_headers
    )

    followers_response = await client.get(
        f"/api/v1/users/{second_user.username}/followers"
    )
    following_response = await client.get(
        f"/api/v1/users/{test_user.username}/following"
    )

    assert followers_response.status_code == 200
    assert followers_response.json()["users"][0]["username"] == test_user.username
    assert following_response.status_code == 200
    assert following_response.json()["users"][0]["username"] == second_user.username


@pytest.mark.asyncio()
async def test_prevent_self_follow(
    client: AsyncClient,
    test_user,
    auth_headers: dict[str, str],
) -> None:
    response = await client.post(
        f"/api/v1/users/{test_user.username}/follow", headers=auth_headers
    )

    assert response.status_code == 400
