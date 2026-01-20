"""积分管理路由"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import get_admin_user, get_current_user
from app.models.auth import User
from app.models.credit import (
    CreditBalance,
    CreditUsageLog,
    InviteCode,
    InviteCodeCreate,
    InviteCodeRead,
)
from app.services.credit_service import create_invite_code, get_invite_code

router = APIRouter()


class InviteCodeDetail(BaseModel):
    """邀请码详情（含使用统计）"""

    code: str
    credits: int
    is_active: bool
    created_at: datetime
    registered_users: int
    total_tokens_used: int


class InviteCodeListResponse(BaseModel):
    """邀请码列表响应"""

    items: List[InviteCodeDetail]
    total: int


class UsageLogItem(BaseModel):
    """使用记录项"""

    id: int
    input_tokens: int
    output_tokens: int
    credits_deducted: int
    model: Optional[str]
    created_at: datetime


class InviteCodeUsageResponse(BaseModel):
    """邀请码使用情况响应"""

    code: str
    credits: int
    is_active: bool
    registered_users: List[dict]
    usage_logs: List[UsageLogItem]
    total_input_tokens: int
    total_output_tokens: int
    total_credits_used: int


@router.get("/balance", response_model=CreditBalance)
async def get_balance(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    查询当前用户积分余额

    Header: Authorization: Bearer <token>
    """
    if not user.invited_by_code:
        raise HTTPException(status_code=400, detail="用户未关联邀请码")

    invite = await get_invite_code(session, user.invited_by_code)
    if not invite:
        raise HTTPException(status_code=404, detail="邀请码不存在")

    return CreditBalance(
        code=invite.code,
        credits=invite.credits,
        is_active=invite.is_active,
    )


@router.post("/admin/invite-codes", response_model=InviteCodeRead)
async def create_invite(
    request: InviteCodeCreate,
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
):
    """
    创建邀请码（管理接口）

    需要管理员权限
    """
    invite = await create_invite_code(
        session,
        credits=request.credits,
        code=request.code,
    )
    return InviteCodeRead(
        code=invite.code,
        credits=invite.credits,
        is_active=invite.is_active,
        created_at=invite.created_at,
    )


@router.get("/admin/invite-codes", response_model=InviteCodeListResponse)
async def list_invite_codes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_active: Optional[bool] = None,
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
):
    """
    获取所有邀请码列表（管理接口，需要管理员权限）
    """
    query = select(InviteCode)
    if is_active is not None:
        query = query.where(InviteCode.is_active == is_active)

    # 总数
    count_result = await session.exec(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.one()

    # 分页
    query = query.order_by(InviteCode.created_at.desc()).offset(skip).limit(limit)
    result = await session.exec(query)
    invites = result.all()

    items = []
    for invite in invites:
        # 统计注册用户数
        user_count_result = await session.exec(
            select(func.count()).where(User.invited_by_code == invite.code)
        )
        registered_users = user_count_result.one()

        # 统计token使用量
        token_result = await session.exec(
            select(
                func.coalesce(
                    func.sum(
                        CreditUsageLog.input_tokens + CreditUsageLog.output_tokens
                    ),
                    0,
                )
            ).where(CreditUsageLog.invite_code == invite.code)
        )
        total_tokens = token_result.one()

        items.append(
            InviteCodeDetail(
                code=invite.code,
                credits=invite.credits,
                is_active=invite.is_active,
                created_at=invite.created_at,
                registered_users=registered_users,
                total_tokens_used=total_tokens,
            )
        )

    return InviteCodeListResponse(items=items, total=total)


@router.get("/admin/invite-codes/{code}", response_model=InviteCodeUsageResponse)
async def get_invite_code_usage(
    code: str,
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
):
    """
    获取单个邀请码的详细使用情况（管理接口，需要管理员权限）
    """
    invite = await get_invite_code(session, code)
    if not invite:
        raise HTTPException(status_code=404, detail="邀请码不存在")

    # 获取使用此邀请码注册的用户
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

    # 获取使用记录
    logs_result = await session.exec(
        select(CreditUsageLog)
        .where(CreditUsageLog.invite_code == code)
        .order_by(CreditUsageLog.created_at.desc())
        .limit(100)
    )
    logs = logs_result.all()

    usage_logs = [
        UsageLogItem(
            id=log.id,
            input_tokens=log.input_tokens,
            output_tokens=log.output_tokens,
            credits_deducted=log.credits_deducted,
            model=log.model,
            created_at=log.created_at,
        )
        for log in logs
    ]

    # 统计总量
    stats_result = await session.exec(
        select(
            func.coalesce(func.sum(CreditUsageLog.input_tokens), 0),
            func.coalesce(func.sum(CreditUsageLog.output_tokens), 0),
            func.coalesce(func.sum(CreditUsageLog.credits_deducted), 0),
        ).where(CreditUsageLog.invite_code == code)
    )
    stats = stats_result.one()

    return InviteCodeUsageResponse(
        code=invite.code,
        credits=invite.credits,
        is_active=invite.is_active,
        registered_users=registered_users,
        usage_logs=usage_logs,
        total_input_tokens=stats[0],
        total_output_tokens=stats[1],
        total_credits_used=stats[2],
    )


@router.patch("/admin/invite-codes/{code}")
async def update_invite_code(
    code: str,
    is_active: Optional[bool] = None,
    add_credits: Optional[int] = None,
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_session),
):
    """
    更新邀请码（启用/禁用、充值积分，需要管理员权限）
    """
    invite = await get_invite_code(session, code)
    if not invite:
        raise HTTPException(status_code=404, detail="邀请码不存在")

    if is_active is not None:
        invite.is_active = is_active

    if add_credits is not None:
        invite.credits += add_credits

    invite.updated_at = datetime.utcnow()
    session.add(invite)
    await session.commit()
    await session.refresh(invite)

    return {
        "code": invite.code,
        "credits": invite.credits,
        "is_active": invite.is_active,
        "message": "更新成功",
    }
