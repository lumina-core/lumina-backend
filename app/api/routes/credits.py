"""积分路由 - 外部接口"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user
from app.models.auth import User
from app.models.credit import CreditBalance
from app.services.credit_service import get_invite_code

router = APIRouter()


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
