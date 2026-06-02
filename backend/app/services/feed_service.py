from uuid import UUID

from redis import RedisError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.follow import Follow
from app.models.post import Post

FEED_MAX_ITEMS = 200
FEED_TTL_SECONDS = 10 * 60


def feed_key(user_id: UUID) -> str:
    return f"feed:{user_id}"


def encode_post_id(post_id: UUID) -> str:
    return str(post_id)


async def get_redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def push_posts_to_feed(user_id: UUID, post_ids: list[UUID]) -> None:
    if not post_ids:
        return
    redis = await get_redis()
    key = feed_key(user_id)
    try:
        await redis.lpush(key, *[encode_post_id(post_id) for post_id in post_ids])
        await redis.ltrim(key, 0, FEED_MAX_ITEMS - 1)
        await redis.expire(key, FEED_TTL_SECONDS)
    except RedisError:
        return
    finally:
        await redis.aclose()


async def seed_follow_feed(
    db: AsyncSession, follower_id: UUID, following_id: UUID
) -> None:
    result = await db.execute(
        select(Post.id)
        .where(Post.author_id == following_id)
        .order_by(Post.created_at.desc())
        .limit(10)
    )
    await push_posts_to_feed(follower_id, list(result.scalars().all()))


async def invalidate_feed(user_id: UUID) -> None:
    redis = await get_redis()
    try:
        await redis.delete(feed_key(user_id))
    except RedisError:
        return
    finally:
        await redis.aclose()


async def fanout_post_to_followers(db: AsyncSession, post: Post) -> None:
    result = await db.execute(
        select(Follow.follower_id).where(Follow.following_id == post.author_id)
    )
    follower_ids = list(result.scalars().all())
    for follower_id in follower_ids:
        await push_posts_to_feed(follower_id, [post.id])


async def read_feed_ids_from_cache(user_id: UUID) -> list[UUID]:
    redis = await get_redis()
    try:
        values = await redis.lrange(feed_key(user_id), 0, FEED_MAX_ITEMS - 1)
    except RedisError:
        return []
    finally:
        await redis.aclose()

    post_ids: list[UUID] = []
    for value in values:
        try:
            post_ids.append(UUID(value))
        except ValueError:
            continue
    return post_ids


async def get_feed_posts(
    db: AsyncSession,
    user_id: UUID,
    page: int = 1,
    size: int = 20,
) -> list[Post]:
    cached_ids = await read_feed_ids_from_cache(user_id)
    if cached_ids:
        page_ids = cached_ids[(page - 1) * size : page * size]
        if not page_ids:
            return []
        result = await db.execute(select(Post).where(Post.id.in_(page_ids)))
        posts_by_id = {post.id: post for post in result.scalars().all()}
        return [posts_by_id[post_id] for post_id in page_ids if post_id in posts_by_id]

    offset = (page - 1) * size
    result = await db.execute(
        select(Post)
        .join(Follow, Follow.following_id == Post.author_id)
        .where(Follow.follower_id == user_id)
        .order_by(Post.created_at.desc())
        .limit(FEED_MAX_ITEMS)
    )
    posts = list(result.scalars().all())
    await push_posts_to_feed(user_id, [post.id for post in posts[:FEED_MAX_ITEMS]])
    return posts[offset : offset + size]
