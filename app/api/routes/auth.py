"""认证路由"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.models.auth import (
    LoginRequest,
    RegisterRequest,
    SendCodeRequest,
    SendCodeResponse,
    TokenResponse,
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
    process_invite_reward,
    user_to_info,
    validate_invite_code,
    verify_email_code,
    verify_password,
)
from app.services.email_service import send_verification_email

router = APIRouter()


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
async def get_current_user(
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """
    获取当前用户信息

    Header: Authorization: Bearer <token>
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")

    token = authorization[7:]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Token无效或已过期")

    user_id = int(payload.get("sub"))
    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用")

    return user_to_info(user)
