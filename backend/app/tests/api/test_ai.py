from types import SimpleNamespace

import pytest
from redis import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import ai_service
from app.services.user_service import create_user


@pytest.mark.asyncio
async def test_extract_skills_with_mocked_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCompletions:
        async def create(self, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='["Python", "FastAPI", "python", 123]'
                        )
                    )
                ]
            )

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(ai_service, "AsyncOpenAI", FakeClient)

    skills = await ai_service.extract_skills("Built APIs with Python and FastAPI.")

    assert skills == ["python", "fastapi"]


@pytest.mark.asyncio
async def test_get_skill_embedding_with_mocked_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEmbeddings:
        async def create(self, **kwargs: object) -> SimpleNamespace:
            assert kwargs["model"] == ai_service.EMBEDDING_MODEL
            assert kwargs["input"] == "python, fastapi"
            return SimpleNamespace(data=[SimpleNamespace(embedding=[1, 0.5, 0])])

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr(ai_service, "AsyncOpenAI", FakeClient)

    embedding = await ai_service.get_skill_embedding(["Python", "FastAPI", "python"])

    assert embedding == [1.0, 0.5, 0.0]


def test_cosine_similarity() -> None:
    assert ai_service.cosine_similarity([1, 0], [1, 0]) == 1
    assert ai_service.cosine_similarity([1, 0], [0, 1]) == 0
    assert ai_service.cosine_similarity([], [1, 0]) == 0
    assert ai_service.cosine_similarity([1, 0], [1]) == 0


@pytest.mark.asyncio
async def test_matches_endpoint_with_mocked_embeddings(
    client,
    db: AsyncSession,
    test_user: User,
    second_user: User,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_user.skills = ["python", "fastapi"]
    second_user.skills = ["python", "redis"]
    db.add_all([test_user, second_user])

    charlie = await create_user(
        db,
        UserCreate(
            email="charlie@example.com", username="charlie", password="password123"
        ),
    )
    charlie.skills = ["go", "kubernetes"]
    db.add(charlie)
    await db.commit()

    async def fake_embedding(skills: list[str]) -> list[float]:
        if "fastapi" in skills:
            return [1.0, 0.0]
        if "redis" in skills:
            return [0.9, 0.1]
        return [0.2, 0.8]

    monkeypatch.setattr(ai_service, "get_skill_embedding", fake_embedding)

    response = await client.get("/api/v1/ai/matches", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["username"] == "bob"
    assert payload[0]["similarity_score"] > payload[1]["similarity_score"]
    assert {match["username"] for match in payload} == {"bob", "charlie"}


@pytest.mark.asyncio
async def test_match_users_falls_back_when_redis_unavailable(
    db: AsyncSession,
    test_user: User,
    second_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_user.skills = ["python", "fastapi"]
    second_user.skills = ["python", "fastapi"]
    db.add_all([test_user, second_user])
    await db.commit()

    async def unavailable_redis() -> object:
        raise RedisError("redis unavailable")

    async def fake_embedding(skills: list[str]) -> list[float]:
        return [1.0, 0.0]

    monkeypatch.setattr(ai_service, "get_redis", unavailable_redis)
    monkeypatch.setattr(ai_service, "get_skill_embedding", fake_embedding)

    matches = await ai_service.match_users(db, test_user)

    assert len(matches) == 1
    assert matches[0].username == "bob"
    assert matches[0].similarity_score == 1


@pytest.mark.asyncio
async def test_generate_and_store_embedding_persists_embedding(
    db: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_user.skills = ["python", "fastapi"]
    await db.commit()

    async def fake_embedding(skills: list[str]) -> list[float]:
        assert skills == ["python", "fastapi"]
        return [0.1, 0.9]

    monkeypatch.setattr(ai_service, "get_skill_embedding", fake_embedding)

    embedding = await ai_service.generate_and_store_embedding(db, test_user)
    await db.commit()
    await db.refresh(test_user)

    assert embedding == [0.1, 0.9]
    assert test_user.embedding == [0.1, 0.9]


@pytest.mark.asyncio
async def test_user_skill_update_stores_embedding(
    client,
    test_user: User,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate(db: AsyncSession, user: User) -> list[float]:
        user.embedding = [0.4, 0.6]
        return [0.4, 0.6]

    monkeypatch.setattr(ai_service, "try_generate_and_store_embedding", fake_generate)

    response = await client.put(
        "/api/v1/users/me",
        json={"skills": ["Python", "FastAPI"]},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert test_user.embedding == [0.4, 0.6]


@pytest.mark.asyncio
async def test_match_users_uses_stored_embeddings_without_openai(
    db: AsyncSession,
    test_user: User,
    second_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_user.skills = ["python"]
    test_user.embedding = [1.0, 0.0]
    second_user.skills = ["fastapi"]
    second_user.embedding = [0.8, 0.2]
    db.add_all([test_user, second_user])
    await db.commit()

    async def fail_embedding(skills: list[str]) -> list[float]:
        raise AssertionError("OpenAI embedding should not be called")

    monkeypatch.setattr(ai_service, "get_skill_embedding", fail_embedding)

    matches = await ai_service.match_users(db, test_user)

    assert len(matches) == 1
    assert matches[0].username == "bob"
    assert matches[0].similarity_score > 0


@pytest.mark.asyncio
async def test_missing_embedding_is_regenerated(
    db: AsyncSession,
    test_user: User,
    second_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_user.skills = ["python"]
    test_user.embedding = [1.0, 0.0]
    second_user.skills = ["redis"]
    second_user.embedding = None
    db.add_all([test_user, second_user])
    await db.commit()

    calls: list[list[str]] = []

    async def fake_embedding(skills: list[str]) -> list[float]:
        calls.append(skills)
        return [0.7, 0.3]

    monkeypatch.setattr(ai_service, "get_skill_embedding", fake_embedding)

    matches = await ai_service.match_users(db, test_user)
    await db.refresh(second_user)

    assert calls == [["redis"]]
    assert second_user.embedding == [0.7, 0.3]
    assert matches[0].username == "bob"


@pytest.mark.asyncio
async def test_reindex_endpoint(
    client,
    db: AsyncSession,
    second_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = await create_user(
        db,
        UserCreate(email="admin@example.com", username="admin", password="password123"),
    )
    admin.is_superuser = True
    second_user.skills = ["python"]
    db.add_all([admin, second_user])
    await db.commit()

    async def fake_embedding(skills: list[str]) -> list[float]:
        return [0.3, 0.7, 0.2]

    monkeypatch.setattr(ai_service, "get_skill_embedding", fake_embedding)

    token = create_access_token({"sub": str(admin.id)})
    response = await client.post(
        f"/api/v1/ai/reindex/{second_user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(second_user.id),
        "embedding_dimensions": 3,
    }
    await db.refresh(second_user)
    assert second_user.embedding == [0.3, 0.7, 0.2]


@pytest.mark.asyncio
async def test_reindex_endpoint_normal_user_gets_403(
    client,
    second_user: User,
    auth_headers: dict[str, str],
) -> None:
    response = await client.post(
        f"/api/v1/ai/reindex/{second_user.id}",
        headers=auth_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"
