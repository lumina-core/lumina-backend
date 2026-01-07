"""积分管理路由"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.models.credit import CreditBalance, InviteCodeCreate, InviteCodeRead
from app.services.credit_service import create_invite_code, get_invite_code

router = APIRouter()


@router.get("/balance", response_model=CreditBalance)
async def get_balance(
    x_invite_code: Optional[str] = Header(None, alias="X-Invite-Code"),
    session: AsyncSession = Depends(get_session),
):
    """
    查询积分余额

    Header: X-Invite-Code - 邀请码
    """
    if not x_invite_code:
        raise HTTPException(status_code=400, detail="缺少邀请码")

    invite = await get_invite_code(session, x_invite_code)
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
    session: AsyncSession = Depends(get_session),
):
    """
    创建邀请码（管理接口）

    生产环境应添加管理员认证
    """
    # TODO: 添加管理员认证
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
