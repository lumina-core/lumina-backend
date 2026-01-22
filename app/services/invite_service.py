"""邀请码服务"""

from datetime import datetime, UTC
from typing import Optional

from loguru import logger
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.auth import InviteRelation, User
from app.models.credit import InviteCode


async def get_user_invite_code(
    session: AsyncSession, user_id: int
) -> Optional[InviteCode]:
    """获取用户的专属邀请码"""
    result = await session.exec(
        select(InviteCode).where(InviteCode.owner_id == user_id)
    )
    return result.one_or_none()


async def create_user_invite_code(session: AsyncSession, user_id: int) -> InviteCode:
    """为用户创建专属邀请码"""
    existing = await get_user_invite_code(session, user_id)
    if existing:
        return existing

    max_attempts = 10
    for _ in range(max_attempts):
        code = InviteCode.generate_code()
        check = await session.exec(select(InviteCode).where(InviteCode.code == code))
        if not check.one_or_none():
            invite_code = InviteCode(
                code=code,
                owner_id=user_id,
                use_count=0,
                credits=0,
                is_active=True,
            )
            session.add(invite_code)
            await session.commit()
            await session.refresh(invite_code)
            logger.info(f"用户 {user_id} 创建邀请码: {code}")
            return invite_code

    raise Exception("无法生成唯一邀请码，请重试")


async def get_or_create_user_invite_code(
    session: AsyncSession, user_id: int
) -> InviteCode:
    """获取或创建用户专属邀请码"""
    invite_code = await get_user_invite_code(session, user_id)
    if not invite_code:
        invite_code = await create_user_invite_code(session, user_id)
    return invite_code


async def get_invite_code_by_code(
    session: AsyncSession, code: str
) -> Optional[InviteCode]:
    """通过邀请码获取邀请码对象"""
    result = await session.exec(select(InviteCode).where(InviteCode.code == code))
    return result.one_or_none()


async def increment_invite_code_use_count(session: AsyncSession, code: str) -> None:
    """增加邀请码使用次数"""
    invite = await get_invite_code_by_code(session, code)
    if invite:
        invite.use_count += 1
        invite.updated_at = datetime.now(UTC)
        session.add(invite)
        await session.commit()


async def get_invite_stats(session: AsyncSession, user_id: int) -> dict:
    """获取用户的邀请统计"""
    result = await session.exec(
        select(
            func.count(InviteRelation.id).label("total_invited"),
            func.sum(InviteRelation.inviter_reward).label("total_reward"),
        ).where(InviteRelation.inviter_id == user_id)
    )
    row = result.one_or_none()

    if row:
        total_invited = row[0] or 0
        total_reward = row[1] or 0
    else:
        total_invited = 0
        total_reward = 0

    return {
        "total_invited": total_invited,
        "total_reward_earned": total_reward,
    }


async def get_invitee_list(
    session: AsyncSession, user_id: int, limit: int = 20, offset: int = 0
) -> tuple[list[dict], int]:
    """获取用户邀请的人员列表"""
    count_result = await session.exec(
        select(func.count(InviteRelation.id)).where(
            InviteRelation.inviter_id == user_id
        )
    )
    total = count_result.one() or 0

    result = await session.exec(
        select(InviteRelation, User)
        .join(User, InviteRelation.invitee_id == User.id)
        .where(InviteRelation.inviter_id == user_id)
        .order_by(InviteRelation.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    invitees = []
    for relation, user in result.all():
        invitees.append(
            {
                "id": user.id,
                "email": _mask_email(user.email),
                "name": user.name,
                "reward_earned": relation.inviter_reward,
                "invited_at": relation.created_at,
            }
        )

    return invitees, total


def _mask_email(email: str) -> str:
    """邮箱脱敏处理: abc@example.com -> a**@example.com"""
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"{local}**@{domain}"
    return f"{local[0]}**@{domain}"


def get_invite_url(code: str) -> str:
    """生成邀请链接"""
    return f"{settings.frontend_url}/register?invite={code}"
