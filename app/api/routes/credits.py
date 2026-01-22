"""积分路由 - 外部接口"""

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_user
from app.models.auth import User
from app.models.credit import UserCreditResponse
from app.services.user_credit_service import get_user_credit_info

router = APIRouter()


@router.get("/balance", response_model=UserCreditResponse)
async def get_balance(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    查询当前用户积分余额

    Header: Authorization: Bearer <token>
    """
    credit_info = await get_user_credit_info(session, user.id)
    return UserCreditResponse(**credit_info)
