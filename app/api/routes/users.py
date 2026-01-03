from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.models.user import User, UserCreate, UserRead

router = APIRouter()


@router.get("", response_model=list[UserRead])
async def list_users(session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(User))
    users = result.all()
    return users


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(User).where(User.id == user_id))
    user = result.one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("", response_model=UserRead, status_code=201)
async def create_user(user: UserCreate, session: AsyncSession = Depends(get_session)):
    db_user = User.model_validate(user)
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


@router.delete("/{user_id}")
async def delete_user(user_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(User).where(User.id == user_id))
    user = result.one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(user)
    await session.commit()
    return {"ok": True}
