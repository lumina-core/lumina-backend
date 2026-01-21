"""认证服务"""

from datetime import datetime, timedelta, UTC
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.auth import EmailVerification, InviteRelation, User, UserInfo
from app.models.credit import InviteCode


def hash_password(password: str) -> str:
    """哈希密码"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def create_access_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """创建访问Token"""
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode = {"sub": str(user_id), "exp": expire, "type": "access"}
    return jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def create_refresh_token(user_id: int) -> str:
    """创建刷新Token"""
    expire = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    to_encode = {"sub": str(user_id), "exp": expire, "type": "refresh"}
    return jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_token(token: str) -> Optional[dict]:
    """解码Token"""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None


async def get_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    """通过邮箱获取用户"""
    result = await session.exec(select(User).where(User.email == email))
    return result.one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    """通过ID获取用户"""
    result = await session.exec(select(User).where(User.id == user_id))
    return result.one_or_none()


async def validate_invite_code(
    session: AsyncSession, code: str
) -> Optional[InviteCode]:
    """验证邀请码是否有效"""
    result = await session.exec(
        select(InviteCode).where(InviteCode.code == code, InviteCode.is_active)
    )
    return result.one_or_none()


async def create_verification_code(
    session: AsyncSession, email: str, purpose: str = "register"
) -> EmailVerification:
    """创建验证码"""
    code = EmailVerification.generate_code()
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.verification_code_expire_minutes
    )

    verification = EmailVerification(
        email=email, code=code, purpose=purpose, expires_at=expires_at
    )
    session.add(verification)
    await session.commit()
    await session.refresh(verification)
    return verification


async def verify_email_code(
    session: AsyncSession, email: str, code: str, purpose: str = "register"
) -> bool:
    """验证邮箱验证码"""
    result = await session.exec(
        select(EmailVerification).where(
            EmailVerification.email == email,
            EmailVerification.code == code,
            EmailVerification.purpose == purpose,
            ~EmailVerification.is_used,
            EmailVerification.expires_at > datetime.now(UTC),
        )
    )
    verification = result.one_or_none()

    if not verification:
        return False

    verification.is_used = True
    session.add(verification)
    await session.commit()
    return True


async def create_user(
    session: AsyncSession,
    email: str,
    password: str,
    invite_code: str,
    name: Optional[str] = None,
) -> User:
    """创建用户"""
    user = User(
        email=email,
        password_hash=hash_password(password),
        name=name,
        invited_by_code=invite_code,
        is_verified=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def process_invite_reward(
    session: AsyncSession, new_user: User, invite_code: str
) -> Optional[InviteRelation]:
    """
    处理邀请奖励（裂变机制）

    如果邀请码属于某个用户，则双方都获得积分奖励
    """
    # 查找邀请码
    result = await session.exec(
        select(InviteCode).where(InviteCode.code == invite_code)
    )
    invite = result.one_or_none()

    if not invite:
        return None

    # 查找使用该邀请码注册的用户（邀请人）
    inviter_result = await session.exec(
        select(User).where(
            User.invited_by_code == invite_code,
            User.id != new_user.id,
        )
    )
    inviter = inviter_result.first()

    inviter_reward = settings.invite_reward_inviter
    invitee_reward = settings.invite_reward_invitee

    # 更新邀请码积分池
    invite.credits += inviter_reward + invitee_reward
    invite.updated_at = datetime.now(UTC)
    session.add(invite)

    # 创建邀请关系记录（修复 bug: inviter_id 应为邀请人 ID）
    relation = InviteRelation(
        inviter_id=inviter.id if inviter else new_user.id,
        invitee_id=new_user.id,
        invite_code=invite_code,
        inviter_reward=inviter_reward,
        invitee_reward=invitee_reward,
    )
    session.add(relation)
    await session.commit()

    logger.info(
        f"邀请奖励已发放: 邀请码={invite_code}, 新用户={new_user.email}, "
        f"奖励积分={inviter_reward + invitee_reward}"
    )
    return relation


def user_to_info(user: User) -> UserInfo:
    """User转UserInfo"""
    return UserInfo(
        id=user.id,
        email=user.email,
        name=user.name,
        is_verified=user.is_verified,
        created_at=user.created_at,
    )
