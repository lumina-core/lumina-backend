"""认证路由"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.deps import get_current_user
from app.models.auth import (
    LoginRequest,
    RegisterRequest,
    SendCodeRequest,
    SendCodeResponse,
    TokenResponse,
    User,
    UserInfo,
    RefreshTokenRequest,
)
from app.services.auth_service import (
    create_access_token,
    create_user,
    create_verification_code,
    decode_token,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    process_invite_reward,
    user_to_info,
    validate_invite_code,
    verify_email_code,
    verify_password,
)
from app.services.credit_service import get_invite_code
from app.services.email_service import send_verification_email

router = APIRouter()


class UpdateUserRequest(BaseModel):
    """修改用户信息请求"""

    name: Optional[str] = Field(None, max_length=100)


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""

    old_password: str = Field(min_length=6)
    new_password: str = Field(min_length=6, max_length=100)


class UserCreditsResponse(BaseModel):
    """用户积分响应"""

    user_id: int
    email: str
    invite_code: Optional[str]
    credits: int
    is_active: bool


@router.post("/send-code", response_model=SendCodeResponse)
async def send_code(
    request: SendCodeRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    发送邮箱验证码

    需要先验证邀请码是否有效
    """
    invite = await validate_invite_code(session, request.invite_code)
    if not invite:
        raise HTTPException(status_code=400, detail="邀请码无效或已停用")

    existing_user = await get_user_by_email(session, request.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    verification = await create_verification_code(session, request.email, "register")

    success = await send_verification_email(request.email, verification.code)
    if not success:
        raise HTTPException(status_code=500, detail="验证码发送失败，请稍后重试")

    return SendCodeResponse(
        success=True,
        message=f"验证码已发送至 {request.email}，{settings.verification_code_expire_minutes}分钟内有效",
    )


@router.post("/register", response_model=TokenResponse)
async def register(
    request: RegisterRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    用户注册

    需要邮箱验证码和有效邀请码
    """
    invite = await validate_invite_code(session, request.invite_code)
    if not invite:
        raise HTTPException(status_code=400, detail="邀请码无效或已停用")

    existing_user = await get_user_by_email(session, request.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    is_valid = await verify_email_code(session, request.email, request.code, "register")
    if not is_valid:
        raise HTTPException(status_code=400, detail="验证码无效或已过期")

    user = await create_user(
        session,
        email=request.email,
        password=request.password,
        invite_code=request.invite_code,
        name=request.name,
    )

    await process_invite_reward(session, user, request.invite_code)

    access_token = create_access_token(user.id)

    logger.info(f"新用户注册: {user.email}, 邀请码: {request.invite_code}")

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=user_to_info(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    用户登录
    """
    user = await get_user_by_email(session, request.email)
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    if not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")

    access_token = create_access_token(user.id)

    logger.info(f"用户登录: {user.email}")

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=user_to_info(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    刷新访问Token
    """
    payload = decode_token(request.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="无效的刷新Token")

    user_id = int(payload.get("sub"))
    user = await get_user_by_id(session, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")

    access_token = create_access_token(user.id)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=user_to_info(user),
    )


@router.get("/me", response_model=UserInfo)
async def get_me(
    user: User = Depends(get_current_user),
):
    """
    获取当前用户信息

    Header: Authorization: Bearer <token>
    """
    return user_to_info(user)


@router.put("/me", response_model=UserInfo)
async def update_me(
    request: UpdateUserRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    修改当前用户信息
    """
    if request.name is not None:
        user.name = request.name

    from datetime import datetime

    user.updated_at = datetime.utcnow()
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return user_to_info(user)


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    修改密码
    """
    if not verify_password(request.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")

    user.password_hash = hash_password(request.new_password)

    from datetime import datetime

    user.updated_at = datetime.utcnow()
    session.add(user)
    await session.commit()

    logger.info(f"用户修改密码: {user.email}")
    return {"message": "密码修改成功"}


@router.get("/me/credits", response_model=UserCreditsResponse)
async def get_my_credits(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    获取当前用户积分余额
    """
    credits = 0
    is_active = False

    if user.invited_by_code:
        invite = await get_invite_code(session, user.invited_by_code)
        if invite:
            credits = invite.credits
            is_active = invite.is_active

    return UserCreditsResponse(
        user_id=user.id,
        email=user.email,
        invite_code=user.invited_by_code,
        credits=credits,
        is_active=is_active,
    )
