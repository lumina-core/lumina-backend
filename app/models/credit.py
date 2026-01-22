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


# ============ 邀请码系统 ============


class InviteCode(SQLModel, table=True):
    """邀请码表"""

    __tablename__ = "invite_codes"

    code: str = Field(primary_key=True, max_length=32)
    owner_id: Optional[int] = Field(
        default=None,
        foreign_key="users.id",
        unique=True,
        index=True,
        description="邀请码所属用户ID（用户专属邀请码）",
    )
    use_count: int = Field(default=0, description="被使用次数")
    is_active: bool = Field(default=True, description="是否启用")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: Optional[datetime] = Field(default=None)

    @staticmethod
    def generate_code(length: int = 6) -> str:
        """生成用户专属邀请码，格式: LUMINA-XXXXXX"""
        chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 排除易混淆字符
        random_part = "".join(secrets.choice(chars) for _ in range(length))
        return f"LUMINA-{random_part}"


class InviteCodeCreate(SQLModel):
    """创建邀请码请求"""

    code: Optional[str] = Field(
        default=None, description="自定义邀请码，不填则自动生成"
    )


class InviteCodeRead(SQLModel):
    """邀请码响应"""

    code: str
    is_active: bool
    created_at: datetime


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


# ============ 邀请码相关响应 ============


class MyInviteCodeResponse(BaseModel):
    """我的邀请码响应"""

    code: str
    use_count: int
    invite_url: str


class InviteStatsResponse(BaseModel):
    """邀请统计响应"""

    total_invited: int
    total_reward_earned: int


class InviteeInfo(BaseModel):
    """被邀请人信息"""

    id: int
    email: str
    name: Optional[str]
    reward_earned: int
    invited_at: datetime


class InviteListResponse(BaseModel):
    """邀请列表响应"""

    invitees: list[InviteeInfo]
    total: int
