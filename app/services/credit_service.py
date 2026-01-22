"""邀请码服务（仅用于邀请码管理，积分统一在 user_credit_service）"""

from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.credit import InviteCode


async def get_invite_code(session: AsyncSession, code: str) -> Optional[InviteCode]:
    """获取邀请码"""
    result = await session.exec(select(InviteCode).where(InviteCode.code == code))
    return result.first()


async def create_invite_code(
    session: AsyncSession,
    code: Optional[str] = None,
) -> InviteCode:
    """创建邀请码"""
    if code is None:
        code = InviteCode.generate_code()

    invite = InviteCode(code=code)
    session.add(invite)
    await session.commit()
    await session.refresh(invite)
    return invite
