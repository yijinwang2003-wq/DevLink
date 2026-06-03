import json
import math
from uuid import UUID

from fastapi import HTTPException, status
from openai import AsyncOpenAI
from redis import RedisError
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.schemas.ai import MatchedUserRead

SKILL_EXTRACTION_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"
MATCH_CACHE_TTL_SECONDS = 60 * 60


def match_cache_key(user_id: UUID) -> str:
    return f"match:{user_id}"


async def get_redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def normalize_skills(skills: list[object]) -> list[str]:
    normalized: list[str] = []
    for skill in skills:
        if not isinstance(skill, str):
            continue
        value = skill.strip().lower()
        if value:
            normalized.append(value)
    return list(dict.fromkeys(normalized))


async def extract_skills(resume_text: str) -> list[str]:
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model=SKILL_EXTRACTION_MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract a JSON array of technical skills from this resume. "
                    "Return ONLY the JSON array, no explanation."
                ),
            },
            {"role": "user", "content": resume_text},
        ],
    )
    content = response.choices[0].message.content or "[]"
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenAI returned invalid skill JSON",
        ) from exc

    if not isinstance(parsed, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenAI returned invalid skill payload",
        )
    return normalize_skills(parsed)


async def get_skill_embedding(skills: list[str]) -> list[float]:
    normalized_skills = normalize_skills(skills)
    if not normalized_skills:
        return []

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=", ".join(normalized_skills),
    )
    return [float(value) for value in response.data[0].embedding]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0

    dot_product = sum(left * right for left, right in zip(a, b))
    norm_a = math.sqrt(sum(value * value for value in a))
    norm_b = math.sqrt(sum(value * value for value in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


async def read_cached_matches(
    db: AsyncSession, user_id: UUID, top_k: int
) -> list[MatchedUserRead] | None:
    redis: Redis | None = None
    try:
        redis = await get_redis()
        cached = await redis.get(match_cache_key(user_id))
    except RedisError:
        return None
    finally:
        if redis is not None:
            await redis.aclose()

    if not cached:
        return None

    try:
        payload = json.loads(cached)
        cache_rows = payload[:top_k]
        user_ids = [UUID(row["id"]) for row in cache_rows]
        scores_by_id = {
            UUID(row["id"]): float(row["similarity_score"]) for row in cache_rows
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    if not user_ids:
        return []

    result = await db.execute(
        select(User).where(User.id.in_(user_ids), User.is_active.is_(True))
    )
    users_by_id = {user.id: user for user in result.scalars().all()}
    return [
        build_matched_user(users_by_id[cached_id], scores_by_id[cached_id])
        for cached_id in user_ids
        if cached_id in users_by_id
    ]


async def write_cached_matches(user_id: UUID, matches: list[MatchedUserRead]) -> None:
    redis: Redis | None = None
    payload = [
        {"id": str(match.id), "similarity_score": match.similarity_score}
        for match in matches
    ]
    try:
        redis = await get_redis()
        await redis.set(
            match_cache_key(user_id),
            json.dumps(payload),
            ex=MATCH_CACHE_TTL_SECONDS,
        )
    except RedisError:
        return
    finally:
        if redis is not None:
            await redis.aclose()


def build_matched_user(user: User, similarity_score: float) -> MatchedUserRead:
    return MatchedUserRead(
        id=user.id,
        email=user.email,
        username=user.username,
        bio=user.bio,
        avatar_url=user.avatar_url,
        skills=user.skills or [],
        github_url=user.github_url,
        created_at=user.created_at,
        similarity_score=similarity_score,
    )


async def match_users(
    db: AsyncSession,
    current_user: User,
    top_k: int = 10,
) -> list[MatchedUserRead]:
    cached_matches = await read_cached_matches(db, current_user.id, top_k)
    if cached_matches is not None:
        return cached_matches

    current_skills = normalize_skills(current_user.skills or [])
    if not current_skills:
        return []

    current_embedding = await get_skill_embedding(current_skills)
    if not current_embedding:
        return []

    result = await db.execute(
        select(User)
        .where(
            User.id != current_user.id,
            User.is_active.is_(True),
            func.cardinality(User.skills) > 0,
        )
        .order_by(User.created_at.desc())
    )
    candidates = list(result.scalars().all())

    matches: list[MatchedUserRead] = []
    for candidate in candidates:
        candidate_embedding = await get_skill_embedding(candidate.skills or [])
        score = cosine_similarity(current_embedding, candidate_embedding)
        if score > 0:
            matches.append(build_matched_user(candidate, score))

    matches.sort(key=lambda match: match.similarity_score, reverse=True)
    top_matches = matches[:top_k]
    await write_cached_matches(current_user.id, top_matches)
    return top_matches
