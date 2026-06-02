from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.post import Post
from app.models.user import User
from app.schemas.post import PostCreate
from app.services.feed_service import fanout_post_to_followers


def normalize_tags(tags: list[str]) -> list[str]:
    normalized_tags = [tag.strip().lower() for tag in tags if tag.strip()]
    return list(dict.fromkeys(normalized_tags))


async def create_post(db: AsyncSession, author: User, post_create: PostCreate) -> Post:
    post = Post(
        author_id=author.id,
        title=post_create.title,
        body=post_create.body,
        tags=normalize_tags(post_create.tags),
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    await fanout_post_to_followers(db, post)
    return post


async def get_post(db: AsyncSession, post_id: UUID) -> Post:
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


async def delete_post(db: AsyncSession, post_id: UUID, current_user: User) -> None:
    post = await get_post(db, post_id)
    if post.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete this post")
    await db.execute(delete(Post).where(Post.id == post_id))
    await db.commit()


async def list_posts_by_author(
    db: AsyncSession,
    author_id: UUID,
    page: int = 1,
    size: int = 20,
) -> list[Post]:
    offset = (page - 1) * size
    result = await db.execute(
        select(Post)
        .where(Post.author_id == author_id)
        .order_by(Post.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    return list(result.scalars().all())
