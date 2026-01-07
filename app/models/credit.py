"""积分和邀请码模型"""

import secrets
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class InviteCode(SQLModel, table=True):
    """邀请码表"""

    __tablename__ = "invite_codes"

    code: str = Field(primary_key=True, max_length=32)
    credits: int = Field(default=0, description="剩余积分")
    is_active: bool = Field(default=True, description="是否启用")
    created_at: datetime = Field(default_factory=datetime.utcnow)
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
    created_at: datetime = Field(default_factory=datetime.utcnow)


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
    """积分余额响应"""

    code: str
    credits: int
    is_active: bool
