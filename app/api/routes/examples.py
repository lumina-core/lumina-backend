"""精选示例路由"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session as get_db_session
from app.core.deps import get_current_user
from app.models.auth import User
from app.models.chat import ChatSession, FeaturedExampleRead, FeaturedExamplesResponse
from app.models.example import (
    ExampleSubmission,
    ExampleSubmissionCreate,
    ExampleSubmissionRead,
    ExampleSubmissionListResponse,
    SubmitExampleResponse,
)
from app.services.chat_service import ChatService

router = APIRouter()

# 每用户每天最多提交次数
MAX_DAILY_SUBMISSIONS = 3


@router.get("", response_model=FeaturedExamplesResponse)
async def get_featured_examples(
    category: Optional[str] = Query(None, description="按分类筛选"),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_db_session),
):
    """
    获取精选示例列表（公开接口，无需登录）

    精选示例来自用户提交并通过审核的优质会话。
    """
    service = ChatService(session)

    categories = await service.get_featured_categories()
    examples = await service.get_featured_examples(category=category, limit=limit)

    return FeaturedExamplesResponse(
        categories=categories,
        examples=[
            FeaturedExampleRead(
                id=ex.id,
                title=ex.title,
                preview=ex.preview,
                category=ex.featured_category,
                share_token=ex.share_token,
                message_count=ex.message_count,
                contributor=ex.featured_contributor,
                created_at=ex.created_at,
            )
            for ex in examples
        ],
    )


@router.post("/submit", response_model=SubmitExampleResponse)
async def submit_example(
    data: ExampleSubmissionCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    提交会话作为使用示例（需要登录）

    提交后进入审核队列，系统会自动审核内容质量和合规性。
    审核通过后会展示在精选示例页面。
    """
    # 检查会话是否存在且属于该用户
    chat_session = await session.get(ChatSession, data.chat_session_id)
    if not chat_session or chat_session.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 检查消息数量
    if chat_session.message_count < 2:
        raise HTTPException(status_code=400, detail="会话消息数量不足，至少需要2条消息")

    # 检查是否已经是精选
    if chat_session.is_featured:
        raise HTTPException(status_code=400, detail="该会话已经是精选示例")

    # 检查是否已提交过（pending/reviewing 状态）
    existing_query = select(ExampleSubmission).where(
        ExampleSubmission.chat_session_id == data.chat_session_id,
        ExampleSubmission.status.in_(["pending", "reviewing"]),
    )
    existing_result = await session.exec(existing_query)
    if existing_result.first():
        raise HTTPException(status_code=400, detail="该会话已在审核队列中")

    # 检查是否最近被拒绝过（24小时内不能重复提交同一会话）
    from datetime import datetime, UTC, timedelta

    rejected_query = select(ExampleSubmission).where(
        ExampleSubmission.chat_session_id == data.chat_session_id,
        ExampleSubmission.status == "rejected",
        ExampleSubmission.reviewed_at >= datetime.now(UTC) - timedelta(hours=24),
    )
    rejected_result = await session.exec(rejected_query)
    if rejected_result.first():
        raise HTTPException(
            status_code=400,
            detail="该会话最近被拒绝，请24小时后再试或提交其他会话",
        )

    # 检查每日提交限制

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    daily_query = select(ExampleSubmission).where(
        ExampleSubmission.user_id == user.id,
        ExampleSubmission.submitted_at >= today_start,
    )
    daily_result = await session.exec(daily_query)
    daily_count = len(list(daily_result.all()))

    if daily_count >= MAX_DAILY_SUBMISSIONS:
        raise HTTPException(
            status_code=429,
            detail=f"每日最多提交 {MAX_DAILY_SUBMISSIONS} 次，请明天再试",
        )

    # 创建提交记录
    submission = ExampleSubmission(
        user_id=user.id,
        chat_session_id=data.chat_session_id,
        display_name=data.display_name[:50],
        status="pending",
    )
    session.add(submission)
    await session.commit()
    await session.refresh(submission)

    return SubmitExampleResponse(
        success=True,
        message="提交成功，系统将自动审核，请耐心等待",
        submission_id=submission.id,
    )


@router.get("/submissions", response_model=ExampleSubmissionListResponse)
async def get_my_submissions(
    status: Optional[str] = Query(
        None, description="按状态筛选: pending/reviewing/approved/rejected"
    ),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    获取我的提交记录（需要登录）
    """
    query = select(ExampleSubmission).where(ExampleSubmission.user_id == user.id)

    if status:
        query = query.where(ExampleSubmission.status == status)

    query = query.order_by(ExampleSubmission.submitted_at.desc()).limit(limit)

    result = await session.exec(query)
    submissions = list(result.all())

    return ExampleSubmissionListResponse(
        total=len(submissions),
        items=[
            ExampleSubmissionRead(
                id=s.id,
                chat_session_id=s.chat_session_id,
                display_name=s.display_name,
                status=s.status,
                llm_score=s.llm_score,
                llm_category=s.llm_category,
                llm_reason=s.llm_reason,
                submitted_at=s.submitted_at,
                reviewed_at=s.reviewed_at,
            )
            for s in submissions
        ],
    )
