import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SkillExtractionRequest(BaseModel):
    resume_text: str = Field(min_length=1)


class SkillExtractionResponse(BaseModel):
    skills: list[str]


class MatchedUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    username: str
    bio: str | None = None
    avatar_url: str | None = None
    skills: list[str] = Field(default_factory=list)
    github_url: str | None = None
    created_at: datetime
    similarity_score: float
