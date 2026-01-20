"""用户管理路由（管理员用）"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.models.auth import User, UserInfo

router = APIRouter()


@router.get("", response_model=list[UserInfo])
async def list_users(session: AsyncSession = Depends(get_session)):
    """获取所有用户列表（管理接口）"""
    result = await session.exec(select(User))
    users = result.all()
    return [
        UserInfo(
            id=u.id,
            email=u.email,
            name=u.name,
            is_verified=u.is_verified,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.get("/{user_id}", response_model=UserInfo)
async def get_user(user_id: int, session: AsyncSession = Depends(get_session)):
    """获取单个用户信息"""
    result = await session.exec(select(User).where(User.id == user_id))
    user = result.one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserInfo(
        id=user.id,
        email=user.email,
        name=user.name,
        is_verified=user.is_verified,
        created_at=user.created_at,
    )


@router.delete("/{user_id}")
async def delete_user(user_id: int, session: AsyncSession = Depends(get_session)):
    """删除用户（管理接口）"""
    result = await session.exec(select(User).where(User.id == user_id))
    user = result.one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await session.delete(user)
    await session.commit()
    return {"ok": True}
