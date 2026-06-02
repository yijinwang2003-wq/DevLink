import uuid

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User).where(func.lower(User.email) == email.lower())
    )
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(
        select(User).where(func.lower(User.username) == username.lower())
    )
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, user_create: UserCreate) -> User:
    existing_email = await get_user_by_email(db, user_create.email)
    if existing_email is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    existing_username = await get_user_by_username(db, user_create.username)
    if existing_username is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already taken"
        )

    user = User(
        email=user_create.email,
        username=user_create.username,
        hashed_password=hash_password(user_create.password),
        skills=[],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user


async def update_user(db: AsyncSession, user: User, user_update: UserUpdate) -> User:
    update_data = user_update.model_dump(exclude_unset=True)
    if "skills" in update_data and update_data["skills"] is not None:
        normalized_skills = [
            skill.strip().lower() for skill in update_data["skills"] if skill.strip()
        ]
        update_data["skills"] = list(dict.fromkeys(normalized_skills))
    for field, value in update_data.items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user


async def list_users(
    db: AsyncSession,
    skill: str | None = None,
    page: int = 1,
    size: int = 20,
) -> list[User]:
    query: Select[tuple[User]] = (
        select(User).where(User.is_active.is_(True)).order_by(User.created_at.desc())
    )
    if skill:
        query = query.where(User.skills.any(skill.lower()))
    offset = (page - 1) * size
    result = await db.execute(query.offset(offset).limit(size))
    return list(result.scalars().all())
