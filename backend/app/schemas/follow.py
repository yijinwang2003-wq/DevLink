from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserRead


class FollowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    follower_id: UUID
    following_id: UUID
    created_at: datetime


class FollowList(BaseModel):
    users: list[UserRead]
