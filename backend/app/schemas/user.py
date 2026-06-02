import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    username: str
    bio: str | None = None
    avatar_url: str | None = None
    skills: list[str] = Field(default_factory=list)
    github_url: str | None = None
    created_at: datetime


class UserUpdate(BaseModel):
    bio: str | None = None
    avatar_url: str | None = None
    github_url: str | None = None
    skills: list[str] | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


class StatusResponse(BaseModel):
    status: str
