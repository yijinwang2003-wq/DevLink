from types import SimpleNamespace

import pytest
from redis import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

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
