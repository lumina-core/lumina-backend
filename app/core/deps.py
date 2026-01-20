"""依赖注入"""

from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.models.auth import User
from app.services.auth_service import decode_token, get_user_by_id


async def get_current_user(
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
) -> User:
    """
    获取当前登录用户（必须登录）

    用法:
        @router.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            ...
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")

    token = authorization[7:]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Token无效或已过期")

    user_id = int(payload.get("sub"))
    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")

    return user


async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
) -> Optional[User]:
    """
    获取当前用户（可选，未登录返回None）
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization[7:]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None

    user_id = int(payload.get("sub"))
    user = await get_user_by_id(session, user_id)
    if not user or not user.is_active:
        return None

    return user


async def get_admin_user(
    user: User = Depends(get_current_user),
) -> User:
    """
    获取管理员用户（必须是管理员）

    用法:
        @router.get("/admin/xxx")
        async def admin_route(user: User = Depends(get_admin_user)):
            ...
    """
    admin_emails = [e.strip() for e in settings.admin_emails.split(",") if e.strip()]

    if not admin_emails:
        raise HTTPException(status_code=403, detail="管理员功能未配置")

    if user.email not in admin_emails:
        raise HTTPException(status_code=403, detail="无管理员权限")

    return user
