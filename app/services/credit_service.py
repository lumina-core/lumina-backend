"""积分服务"""

from datetime import datetime, UTC
from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.credit import CreditUsageLog, InviteCode


# 积分计算配置: 1积分 = 10000 tokens
# 输出 token 通常更贵，设置为输入的 3 倍
INPUT_TOKENS_PER_CREDIT = 10000
OUTPUT_TOKENS_PER_CREDIT = 3330  # 输出更贵


def calculate_credits(input_tokens: int, output_tokens: int) -> int:
    """根据 token 用量计算需要扣除的积分"""
    input_credits = (
        input_tokens + INPUT_TOKENS_PER_CREDIT - 1
    ) // INPUT_TOKENS_PER_CREDIT
    output_credits = (
        output_tokens + OUTPUT_TOKENS_PER_CREDIT - 1
    ) // OUTPUT_TOKENS_PER_CREDIT
    return input_credits + output_credits


async def get_invite_code(session: AsyncSession, code: str) -> Optional[InviteCode]:
    """获取邀请码"""
    result = await session.exec(select(InviteCode).where(InviteCode.code == code))
    return result.first()


async def validate_invite_code(session: AsyncSession, code: str) -> tuple[bool, str]:
    """
    验证邀请码是否有效

    Returns:
        (is_valid, error_message)
    """
    invite = await get_invite_code(session, code)

    if not invite:
        return False, "邀请码不存在"

    if not invite.is_active:
        return False, "邀请码已禁用"

    if invite.credits <= 0:
        return False, "积分余额不足"

    return True, ""


async def deduct_credits(
    session: AsyncSession,
    code: str,
    input_tokens: int,
    output_tokens: int,
    model: Optional[str] = None,
) -> tuple[int, int]:
    """
    扣除积分并记录使用日志

    Returns:
        (credits_deducted, remaining_credits)
    """
    invite = await get_invite_code(session, code)
    if not invite:
        raise ValueError("邀请码不存在")

    credits_needed = calculate_credits(input_tokens, output_tokens)

    # 实际扣除不超过余额
    credits_deducted = min(credits_needed, invite.credits)
    invite.credits -= credits_deducted
    invite.updated_at = datetime.now(UTC)

    # 记录使用日志
    log = CreditUsageLog(
        invite_code=code,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        credits_deducted=credits_deducted,
        model=model,
    )

    session.add(invite)
    session.add(log)
    await session.commit()

    return credits_deducted, invite.credits


async def create_invite_code(
    session: AsyncSession,
    credits: int = 10000,
    code: Optional[str] = None,
) -> InviteCode:
    """创建邀请码"""
    if code is None:
        code = InviteCode.generate_code()

    invite = InviteCode(code=code, credits=credits)
    session.add(invite)
    await session.commit()
    await session.refresh(invite)
    return invite
