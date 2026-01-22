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
from app.services.email_service import send_verification_email
from app.services.user_credit_service import (
    get_or_create_user_credit,
    get_user_credit_info,
    daily_checkin,
)
from app.services.invite_service import (
    get_or_create_user_invite_code,
    get_invite_stats,
    get_invitee_list,
    get_invite_url,
)
from app.models.credit import (
    UserCreditResponse,
    CheckinResponse,
    MyInviteCodeResponse,
    InviteStatsResponse,
    InviteListResponse,
    InviteeInfo,
)

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

    邀请码可选，如果提供则验证其有效性
    """
    # 如果提供了邀请码，验证其有效性
    if request.invite_code:
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

    邀请码可选，有邀请码可获得额外积分奖励
    """
    # 如果提供了邀请码，验证其有效性
    invite = None
    if request.invite_code:
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

    # 创建用户积分账户（会自动赠送注册积分）
    await get_or_create_user_credit(session, user.id)

    # 为新用户创建专属邀请码
    await get_or_create_user_invite_code(session, user.id)

    # 如果有邀请码，处理邀请奖励
    if invite and request.invite_code:
        await process_invite_reward(session, user, request.invite_code)

    access_token = create_access_token(user.id)

    logger.info(f"新用户注册: {user.email}, 邀请码: {request.invite_code or '无'}")

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

    from datetime import datetime, UTC

    user.updated_at = datetime.now(UTC)
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

    from datetime import datetime, UTC

    user.updated_at = datetime.now(UTC)
    session.add(user)
    await session.commit()

    logger.info(f"用户修改密码: {user.email}")
    return {"success": True, "message": "密码修改成功"}


@router.get("/me/credits", response_model=UserCreditResponse)
async def get_my_credits(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    获取当前用户积分余额和使用情况
    """
    credit_info = await get_user_credit_info(session, user.id)
    return UserCreditResponse(**credit_info)


@router.post("/me/checkin", response_model=CheckinResponse)
async def checkin(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    每日签到，获取积分
    """
    success, message, credits_earned, current_credits = await daily_checkin(
        session, user.id
    )
    return CheckinResponse(
        success=success,
        message=message,
        credits_earned=credits_earned,
        current_credits=current_credits,
        streak_days=1,  # 暂时固定为1，后续可以实现连续签到
    )


# ============ 邀请码相关接口 ============


@router.get("/me/invite-code", response_model=MyInviteCodeResponse)
async def get_my_invite_code(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    获取当前用户的专属邀请码
    """
    invite_code = await get_or_create_user_invite_code(session, user.id)
    return MyInviteCodeResponse(
        code=invite_code.code,
        use_count=invite_code.use_count,
        invite_url=get_invite_url(invite_code.code),
    )


@router.get("/me/invite-stats", response_model=InviteStatsResponse)
async def get_my_invite_stats(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    获取邀请统计（邀请人数、获得积分）
    """
    stats = await get_invite_stats(session, user.id)
    return InviteStatsResponse(**stats)


@router.get("/me/invitees", response_model=InviteListResponse)
async def get_my_invitees(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = 20,
    offset: int = 0,
):
    """
    获取邀请的用户列表
    """
    invitees, total = await get_invitee_list(session, user.id, limit, offset)
    return InviteListResponse(
        invitees=[InviteeInfo(**i) for i in invitees],
        total=total,
    )
