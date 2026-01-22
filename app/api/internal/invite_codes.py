"""邀请码管理 - 内部接口"""

from datetime import datetime, UTC
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.models.auth import User
from app.models.credit import InviteCode, InviteCodeCreate, InviteCodeRead
from app.services.credit_service import create_invite_code, get_invite_code

router = APIRouter()


class InviteCodeDetail(BaseModel):
    code: str
    is_active: bool
    created_at: datetime
    registered_users: int
    use_count: int


class InviteCodeListResponse(BaseModel):
    items: List[InviteCodeDetail]
    total: int


class InviteCodeUsageResponse(BaseModel):
    code: str
    is_active: bool
    registered_users: List[dict]
    use_count: int


@router.post("", response_model=InviteCodeRead)
async def create_invite(
    request: InviteCodeCreate,
    session: AsyncSession = Depends(get_session),
):
    """创建邀请码"""
    invite = await create_invite_code(
        session,
        code=request.code,
    )
    return InviteCodeRead(
        code=invite.code,
        is_active=invite.is_active,
        created_at=invite.created_at,
    )


@router.get("", response_model=InviteCodeListResponse)
async def list_invite_codes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_active: Optional[bool] = None,
    session: AsyncSession = Depends(get_session),
):
    """获取所有邀请码列表"""
    query = select(InviteCode)
    if is_active is not None:
        query = query.where(InviteCode.is_active == is_active)

    count_result = await session.exec(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.one()

    query = query.order_by(InviteCode.created_at.desc()).offset(skip).limit(limit)
    result = await session.exec(query)
    invites = result.all()

    items = []
    for invite in invites:
        user_count_result = await session.exec(
            select(func.count()).where(User.invited_by_code == invite.code)
        )
        registered_users = user_count_result.one()

        items.append(
            InviteCodeDetail(
                code=invite.code,
                is_active=invite.is_active,
                created_at=invite.created_at,
                registered_users=registered_users,
                use_count=invite.use_count,
            )
        )

    return InviteCodeListResponse(items=items, total=total)


@router.get("/{code}", response_model=InviteCodeUsageResponse)
async def get_invite_code_usage(
    code: str,
    session: AsyncSession = Depends(get_session),
):
    """获取单个邀请码的详细使用情况"""
    invite = await get_invite_code(session, code)
    if not invite:
        raise HTTPException(status_code=404, detail="邀请码不存在")

    users_result = await session.exec(
        select(User)
        .where(User.invited_by_code == code)
        .order_by(User.created_at.desc())
    )
    users = users_result.all()
    registered_users = [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]

    return InviteCodeUsageResponse(
        code=invite.code,
        is_active=invite.is_active,
        registered_users=registered_users,
        use_count=invite.use_count,
    )


@router.patch("/{code}")
async def update_invite_code(
    code: str,
    is_active: Optional[bool] = None,
    session: AsyncSession = Depends(get_session),
):
    """更新邀请码（启用/禁用）"""
    invite = await get_invite_code(session, code)
    if not invite:
        raise HTTPException(status_code=404, detail="邀请码不存在")

    if is_active is not None:
        invite.is_active = is_active

    invite.updated_at = datetime.now(UTC)
    session.add(invite)
    await session.commit()
    await session.refresh(invite)

    return {
        "code": invite.code,
        "is_active": invite.is_active,
        "use_count": invite.use_count,
    }
