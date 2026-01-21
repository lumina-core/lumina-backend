"""调整用户积分脚本

使用方式:
    uv run -m scripts.adjust_credits <email> <amount> [--reason <reason>]

示例:
    uv run -m scripts.adjust_credits user@example.com 100          # 加100积分
    uv run -m scripts.adjust_credits user@example.com -50          # 减50积分
    uv run -m scripts.adjust_credits user@example.com 500 --reason "活动奖励"
"""

import argparse
import asyncio
import sys

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import engine
from app.models.auth import User
from app.models.credit import UserCredit, UserCreditLog


async def adjust_credits(email: str, amount: int, reason: str | None = None):
    """调整指定用户的积分"""
    async with AsyncSession(engine) as session:
        # 查找用户
        result = await session.exec(select(User).where(User.email == email))
        user = result.first()

        if not user:
            print(f"错误: 找不到用户 {email}")
            return False

        user_id = user.id  # 提前保存，避免 commit 后访问

        # 查找或创建积分记录
        credit_result = await session.exec(
            select(UserCredit).where(UserCredit.user_id == user_id)
        )
        user_credit = credit_result.first()

        if not user_credit:
            user_credit = UserCredit(user_id=user_id, credits=0)
            session.add(user_credit)

        old_balance = user_credit.credits
        new_balance = old_balance + amount

        if new_balance < 0:
            print(f"错误: 积分不足，当前余额 {old_balance}，尝试减少 {abs(amount)}")
            return False

        # 更新积分
        user_credit.credits = new_balance
        if amount > 0:
            user_credit.total_earned += amount
        else:
            user_credit.total_used += abs(amount)

        # 记录日志
        log = UserCreditLog(
            user_id=user_id,
            amount=amount,
            balance=new_balance,
            type="admin_adjust",
            description=reason or ("管理员加积分" if amount > 0 else "管理员扣积分"),
        )
        session.add(log)

        await session.commit()

        action = "增加" if amount > 0 else "减少"
        print(f"成功: 用户 {email} (ID: {user_id})")
        print(f"  {action} {abs(amount)} 积分")
        print(f"  余额: {old_balance} -> {new_balance}")
        if reason:
            print(f"  原因: {reason}")

        return True


def main():
    parser = argparse.ArgumentParser(description="调整用户积分")
    parser.add_argument("email", help="用户邮箱")
    parser.add_argument("amount", type=int, help="调整数量（正数加分，负数减分）")
    parser.add_argument("--reason", "-r", help="调整原因")

    args = parser.parse_args()

    success = asyncio.run(adjust_credits(args.email, args.amount, args.reason))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
