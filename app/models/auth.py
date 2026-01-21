"""认证相关模型"""

import secrets
from datetime import datetime
from typing import Optional

from pydantic import EmailStr
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """用户表"""

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    password_hash: str = Field(max_length=255)
    name: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False)
    invited_by_code: Optional[str] = Field(
        default=None, foreign_key="invite_codes.code", description="注册时使用的邀请码"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)


class EmailVerification(SQLModel, table=True):
    """邮箱验证码表"""

    __tablename__ = "email_verifications"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: EmailStr = Field(index=True, max_length=255)
    code: str = Field(max_length=6, description="6位验证码")
    purpose: str = Field(
        max_length=20, default="register", description="用途: register/login/reset"
    )
    is_used: bool = Field(default=False)
    expires_at: datetime = Field(description="过期时间")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @staticmethod
    def generate_code() -> str:
        """生成6位数字验证码"""
        return "".join(secrets.choice("0123456789") for _ in range(6))


class InviteRelation(SQLModel, table=True):
    """邀请关系表（用于裂变追踪）"""

    __tablename__ = "invite_relations"

    id: Optional[int] = Field(default=None, primary_key=True)
    inviter_id: int = Field(foreign_key="users.id", index=True, description="邀请人ID")
    invitee_id: int = Field(
        foreign_key="users.id", unique=True, description="被邀请人ID"
    )
    invite_code: str = Field(
        foreign_key="invite_codes.code", description="使用的邀请码"
    )
    inviter_reward: int = Field(default=0, description="邀请人获得的积分奖励")
    invitee_reward: int = Field(default=0, description="被邀请人获得的积分奖励")
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============ Request/Response Schemas ============


class SendCodeRequest(SQLModel):
    """发送验证码请求"""

    email: EmailStr
    invite_code: Optional[str] = Field(default=None, description="邀请码（可选）")


class SendCodeResponse(SQLModel):
    """发送验证码响应"""

    success: bool
    message: str


class RegisterRequest(SQLModel):
    """注册请求"""

    email: EmailStr
    code: str = Field(min_length=6, max_length=6, description="邮箱验证码")
    password: str = Field(min_length=6, max_length=100, description="密码")
    name: Optional[str] = Field(default=None, max_length=100)
    invite_code: Optional[str] = Field(
        default=None, description="邀请码（可选，有邀请码可获得额外积分）"
    )


class LoginRequest(SQLModel):
    """登录请求"""

    email: EmailStr
    password: str


class TokenResponse(SQLModel):
    """Token响应"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserInfo"


class UserInfo(SQLModel):
    """用户信息"""

    id: int
    email: EmailStr
    name: Optional[str]
    is_verified: bool
    created_at: datetime


class RefreshTokenRequest(SQLModel):
    """刷新Token请求"""

    refresh_token: str
