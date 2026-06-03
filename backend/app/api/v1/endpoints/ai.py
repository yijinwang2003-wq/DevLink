from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai import (
    MatchedUserRead,
    SkillExtractionRequest,
    SkillExtractionResponse,
)
from app.services import ai_service

router = APIRouter()


@router.post("/extract-skills", response_model=SkillExtractionResponse)
async def extract_resume_skills(
    request: SkillExtractionRequest,
    current_user: User = Depends(get_current_user),
) -> SkillExtractionResponse:
    skills = await ai_service.extract_skills(request.resume_text)
    return SkillExtractionResponse(skills=skills)


@router.get("/matches", response_model=list[MatchedUserRead])
async def matches(
    top_k: Annotated[int, Query(ge=1, le=50)] = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MatchedUserRead]:
    return await ai_service.match_users(db, current_user, top_k=top_k)
