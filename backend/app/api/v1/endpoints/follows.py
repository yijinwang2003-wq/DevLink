from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.follow import FollowList, FollowRead
from app.schemas.user import StatusResponse
from app.services.follow_service import follow_user, list_followers, list_following, unfollow_user

router = APIRouter()


@router.post("/{username}/follow", response_model=FollowRead, status_code=status.HTTP_201_CREATED)
async def follow(
    username: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FollowRead:
    return await follow_user(db, current_user, username)


@router.delete("/{username}/follow", response_model=StatusResponse)
async def unfollow(
    username: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StatusResponse:
    await unfollow_user(db, current_user, username)
    return StatusResponse(status="ok")


@router.get("/{username}/followers", response_model=FollowList)
async def followers(
    username: str,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
) -> FollowList:
    users = await list_followers(db, username, page=page, size=size)
    return FollowList(users=users)


@router.get("/{username}/following", response_model=FollowList)
async def following(
    username: str,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
) -> FollowList:
    users = await list_following(db, username, page=page, size=size)
    return FollowList(users=users)
