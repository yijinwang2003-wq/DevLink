from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.post import PostCreate, PostRead
from app.schemas.user import StatusResponse
from app.services.feed_service import get_feed_posts
from app.services.post_service import create_post, delete_post, get_post

router = APIRouter()
feed_router = APIRouter()


@router.post("/", response_model=PostRead, status_code=status.HTTP_201_CREATED)
async def create(
    post_create: PostCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PostRead:
    return await create_post(db, current_user, post_create)


@router.get("/{post_id}", response_model=PostRead)
async def read(post_id: UUID, db: AsyncSession = Depends(get_db)) -> PostRead:
    return await get_post(db, post_id)


@router.delete("/{post_id}", response_model=StatusResponse)
async def delete(
    post_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StatusResponse:
    await delete_post(db, post_id, current_user)
    return StatusResponse(status="ok")


@feed_router.get("/", response_model=list[PostRead])
async def feed(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PostRead]:
    return await get_feed_posts(db, current_user.id, page=page, size=size)
