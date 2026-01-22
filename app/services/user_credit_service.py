"""用户积分服务"""

from datetime import datetime, date, UTC
from typing import Optional, Tuple

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.credit import UserCredit, UserCreditLog

# 积分配置
DAILY_CHECKIN_CREDITS = 100  # 每日签到赠送积分
DAILY_LIMIT_FREE = 100  # 免费用户每日限额
REGISTER_BONUS = 100  # 注册赠送积分
INVITE_BONUS_INVITER = 500  # 邀请人奖励
INVITE_BONUS_INVITEE = 500  # 被邀请人奖励


async def get_or_create_user_credit(session: AsyncSession, user_id: int) -> UserCredit:
    """获取或创建用户积分账户"""
    query = select(UserCredit).where(UserCredit.user_id == user_id)
    result = await session.exec(query)
    credit = result.first()

    if not credit:
        credit = UserCredit(
            user_id=user_id,
            credits=REGISTER_BONUS,
            total_earned=REGISTER_BONUS,
            daily_limit=DAILY_LIMIT_FREE,
        )
        session.add(credit)

        # 记录注册赠送
        log = UserCreditLog(
            user_id=user_id,
            amount=REGISTER_BONUS,
            balance=REGISTER_BONUS,
            type="bonus",
            description="注册赠送",
        )
        session.add(log)
        await session.commit()
        await session.refresh(credit)

    return credit


async def reset_daily_usage_if_needed(
    session: AsyncSession, credit: UserCredit
) -> UserCredit:
    """如果是新的一天，重置每日使用量"""
    today = date.today()

    # 检查是否需要重置（通过 updated_at 的日期判断）
    if credit.updated_at.date() < today:
        credit.daily_used = 0
        credit.updated_at = datetime.now(UTC)
        session.add(credit)
        await session.commit()
        await session.refresh(credit)

    return credit


async def get_user_credit_info(session: AsyncSession, user_id: int) -> dict:
    """获取用户积分信息"""
    credit = await get_or_create_user_credit(session, user_id)
    credit = await reset_daily_usage_if_needed(session, credit)

    today = date.today()
    checked_in_today = credit.last_checkin_date == today
    daily_remaining = max(0, credit.daily_limit - credit.daily_used)

    return {
        "user_id": user_id,
        "credits": credit.credits,
        "daily_used": credit.daily_used,
        "daily_limit": credit.daily_limit,
        "daily_remaining": daily_remaining,
        "can_use": credit.credits > 0 and daily_remaining > 0,
        "last_checkin_date": credit.last_checkin_date,
        "checked_in_today": checked_in_today,
    }


async def daily_checkin(
    session: AsyncSession, user_id: int
) -> Tuple[bool, str, int, int]:
    """
    每日签到
    返回: (success, message, credits_earned, current_credits)
    """
    credit = await get_or_create_user_credit(session, user_id)
    credit = await reset_daily_usage_if_needed(session, credit)

    today = date.today()

    if credit.last_checkin_date == today:
        return False, "今日已签到", 0, credit.credits

    # 执行签到
    credit.credits += DAILY_CHECKIN_CREDITS
    credit.total_earned += DAILY_CHECKIN_CREDITS
    credit.last_checkin_date = today
    credit.updated_at = datetime.now(UTC)
    session.add(credit)

    # 记录日志
    log = UserCreditLog(
        user_id=user_id,
        amount=DAILY_CHECKIN_CREDITS,
        balance=credit.credits,
        type="checkin",
        description="每日签到",
    )
    session.add(log)

    await session.commit()
    await session.refresh(credit)

    logger.info(f"用户 {user_id} 签到成功，获得 {DAILY_CHECKIN_CREDITS} 积分")
    return True, "签到成功", DAILY_CHECKIN_CREDITS, credit.credits


async def add_user_credits(
    session: AsyncSession,
    user_id: int,
    amount: int,
    credit_type: str = "bonus",
    description: str = "",
) -> UserCredit:
    """通用增加用户积分方法"""
    credit = await get_or_create_user_credit(session, user_id)
    credit.credits += amount
    credit.total_earned += amount
    credit.updated_at = datetime.now(UTC)
    session.add(credit)

    log = UserCreditLog(
        user_id=user_id,
        amount=amount,
        balance=credit.credits,
        type=credit_type,
        description=description,
    )
    session.add(log)

    # 注意：不在这里 commit，由调用方统一 commit
    return credit


async def add_invite_bonus(
    session: AsyncSession, inviter_id: int, invitee_id: int
) -> None:
    """添加邀请奖励"""
    # 邀请人奖励
    inviter_credit = await get_or_create_user_credit(session, inviter_id)
    inviter_credit.credits += INVITE_BONUS_INVITER
    inviter_credit.total_earned += INVITE_BONUS_INVITER
    inviter_credit.updated_at = datetime.now(UTC)
    session.add(inviter_credit)

    log1 = UserCreditLog(
        user_id=inviter_id,
        amount=INVITE_BONUS_INVITER,
        balance=inviter_credit.credits,
        type="invite",
        description=f"邀请用户 {invitee_id} 注册奖励",
    )
    session.add(log1)

    # 被邀请人奖励
    invitee_credit = await get_or_create_user_credit(session, invitee_id)
    invitee_credit.credits += INVITE_BONUS_INVITEE
    invitee_credit.total_earned += INVITE_BONUS_INVITEE
    invitee_credit.updated_at = datetime.now(UTC)
    session.add(invitee_credit)

    log2 = UserCreditLog(
        user_id=invitee_id,
        amount=INVITE_BONUS_INVITEE,
        balance=invitee_credit.credits,
        type="invite",
        description="使用邀请码注册奖励",
    )
    session.add(log2)

    await session.commit()
    logger.info(
        f"邀请奖励已发放: 邀请人 {inviter_id} +{INVITE_BONUS_INVITER}, 被邀请人 {invitee_id} +{INVITE_BONUS_INVITEE}"
    )


async def deduct_user_credits(
    session: AsyncSession,
    user_id: int,
    input_tokens: int,
    output_tokens: int,
    model: str = "unknown",
) -> Tuple[int, int]:
    """
    扣除用户积分
    返回: (credits_deducted, remaining_credits)
    """
    credit = await get_or_create_user_credit(session, user_id)
    credit = await reset_daily_usage_if_needed(session, credit)

    # 计算消耗积分 (简单按 token 数计算，可调整)
    total_tokens = input_tokens + output_tokens
    credits_to_deduct = max(1, total_tokens // 1000)  # 每1000 token 消耗1积分

    # 检查每日限额
    daily_remaining = credit.daily_limit - credit.daily_used
    if daily_remaining <= 0:
        raise ValueError("今日使用额度已用完，请明日再来")

    # 检查余额，不足时扣到0为止
    if credit.credits <= 0:
        raise ValueError("积分不足，请签到获取积分")

    # 实际扣除的积分（不超过剩余积分）
    actual_deduct = min(credits_to_deduct, credit.credits)
    credits_to_deduct = actual_deduct

    # 扣除积分
    credit.credits -= credits_to_deduct
    credit.total_used += credits_to_deduct
    credit.daily_used += credits_to_deduct
    credit.updated_at = datetime.now(UTC)
    session.add(credit)

    # 记录日志
    log = UserCreditLog(
        user_id=user_id,
        amount=-credits_to_deduct,
        balance=credit.credits,
        type="usage",
        description=f"对话消耗 ({model}: {input_tokens}+{output_tokens} tokens)",
    )
    session.add(log)

    await session.commit()
    await session.refresh(credit)

    return credits_to_deduct, credit.credits


async def validate_user_can_chat(
    session: AsyncSession, user_id: int
) -> Tuple[bool, Optional[str]]:
    """验证用户是否可以聊天"""
    credit = await get_or_create_user_credit(session, user_id)
    credit = await reset_daily_usage_if_needed(session, credit)

    if credit.credits <= 0:
        return False, "积分不足，请签到获取积分"

    daily_remaining = credit.daily_limit - credit.daily_used
    if daily_remaining <= 0:
        return False, "今日使用额度已用完，请明日再来"

    return True, None
