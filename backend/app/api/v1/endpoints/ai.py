from typing import Annotated

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai import (
    EmbeddingReindexResponse,
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


@router.post("/reindex/{user_id}", response_model=EmbeddingReindexResponse)
async def reindex_user_embedding(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EmbeddingReindexResponse:
    if current_user.username != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    embedding = await ai_service.generate_and_store_embedding(db, user)
    await db.commit()
    await db.refresh(user)
    return EmbeddingReindexResponse(
        user_id=user.id, embedding_dimensions=len(embedding)
    )
