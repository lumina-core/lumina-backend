"""积分和邀请码模型"""

import secrets
from datetime import datetime, date, UTC
from typing import Optional

from pydantic import BaseModel
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(UTC)


# ============ 用户积分系统 ============


class UserCredit(SQLModel, table=True):
    """用户积分表"""

    __tablename__ = "user_credits"

    user_id: int = Field(primary_key=True, foreign_key="users.id")
    credits: int = Field(default=0, description="当前积分余额")
    total_earned: int = Field(default=0, description="累计获得积分")
    total_used: int = Field(default=0, description="累计使用积分")
    daily_used: int = Field(default=0, description="今日已使用积分")
    daily_limit: int = Field(default=100, description="每日使用上限")
    last_checkin_date: Optional[date] = Field(default=None, description="上次签到日期")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class UserCreditLog(SQLModel, table=True):
    """用户积分变动记录"""

    __tablename__ = "user_credit_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="users.id")
    amount: int = Field(description="变动数量，正数增加负数减少")
    balance: int = Field(description="变动后余额")
    type: str = Field(max_length=20, description="类型: checkin/invite/usage/bonus")
    description: Optional[str] = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=utc_now)


# ============ 邀请码系统（可选，用于额外奖励）============


class InviteCode(SQLModel, table=True):
    """邀请码表"""

    __tablename__ = "invite_codes"

    code: str = Field(primary_key=True, max_length=32)
    credits: int = Field(default=0, description="剩余积分")
    is_active: bool = Field(default=True, description="是否启用")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = Field(default=None)

    @staticmethod
    def generate_code(length: int = 16) -> str:
        """生成随机邀请码"""
        return secrets.token_urlsafe(length)[:length].upper()


class CreditUsageLog(SQLModel, table=True):
    """积分使用记录"""

    __tablename__ = "credit_usage_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    invite_code: str = Field(index=True, foreign_key="invite_codes.code")
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    credits_deducted: int = Field(default=0)
    model: Optional[str] = Field(default=None, max_length=100)
    created_at: datetime = Field(default_factory=utc_now)


class InviteCodeCreate(SQLModel):
    """创建邀请码请求"""

    credits: int = Field(default=10000, ge=0, description="初始积分")
    code: Optional[str] = Field(
        default=None, description="自定义邀请码，不填则自动生成"
    )


class InviteCodeRead(SQLModel):
    """邀请码响应"""

    code: str
    credits: int
    is_active: bool
    created_at: datetime


class CreditBalance(SQLModel):
    """积分余额响应（旧版，兼容邀请码）"""

    code: str
    credits: int
    is_active: bool


# ============ 新版用户积分响应 ============


class UserCreditResponse(BaseModel):
    """用户积分余额响应"""

    user_id: int
    credits: int
    daily_used: int
    daily_limit: int
    daily_remaining: int
    can_use: bool
    last_checkin_date: Optional[date]
    checked_in_today: bool


class CheckinResponse(BaseModel):
    """签到响应"""

    success: bool
    message: str
    credits_earned: int
    current_credits: int
    streak_days: int  # 连续签到天数（预留）
