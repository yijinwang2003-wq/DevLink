from fastapi import HTTPException, status
from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.follow import Follow
from app.models.user import User
from app.services.feed_service import invalidate_feed, seed_follow_feed
from app.services.user_service import get_user_by_username


async def is_following(db: AsyncSession, follower: User, following: User) -> bool:
    result = await db.execute(
        select(
            exists().where(
                Follow.follower_id == follower.id,
                Follow.following_id == following.id,
            )
        )
    )
    return bool(result.scalar())


async def follow_user(db: AsyncSession, follower: User, username: str) -> Follow:
    following = await get_user_by_username(db, username)
    if following is None or not following.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    if follower.id == following.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot follow yourself"
        )
    if await is_following(db, follower, following):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Already following user"
        )

    follow = Follow(follower_id=follower.id, following_id=following.id)
    db.add(follow)
    await db.commit()
    await db.refresh(follow)
    await seed_follow_feed(db, follower.id, following.id)
    return follow


async def unfollow_user(db: AsyncSession, follower: User, username: str) -> None:
    following = await get_user_by_username(db, username)
    if following is None or not following.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    await db.execute(
        delete(Follow).where(
            Follow.follower_id == follower.id,
            Follow.following_id == following.id,
        )
    )
    await db.commit()
    await invalidate_feed(follower.id)


async def list_followers(
    db: AsyncSession,
    username: str,
    page: int = 1,
    size: int = 20,
) -> list[User]:
    user = await get_user_by_username(db, username)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    offset = (page - 1) * size
    result = await db.execute(
        select(User)
        .join(Follow, Follow.follower_id == User.id)
        .where(Follow.following_id == user.id)
        .order_by(Follow.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    return list(result.scalars().all())


async def list_following(
    db: AsyncSession,
    username: str,
    page: int = 1,
    size: int = 20,
) -> list[User]:
    user = await get_user_by_username(db, username)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    offset = (page - 1) * size
    result = await db.execute(
        select(User)
        .join(Follow, Follow.following_id == User.id)
        .where(Follow.follower_id == user.id)
        .order_by(Follow.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    return list(result.scalars().all())
