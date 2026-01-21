"""精选示例路由"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session as get_db_session
from app.models.chat import FeaturedExampleRead, FeaturedExamplesResponse
from app.services.chat_service import ChatService

router = APIRouter()


def _build_share_url(share_token: str) -> str:
    """构建分享 URL"""
    frontend_url = "https://lumina.example.com"  # TODO: 从配置读取
    return f"{frontend_url}/share/{share_token}"


@router.get("", response_model=FeaturedExamplesResponse)
async def get_featured_examples(
    category: Optional[str] = Query(None, description="按分类筛选"),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_db_session),
):
    """
    获取精选示例列表（公开接口，无需登录）

    精选示例是管理员从用户分享的优质会话中挑选的典型用例。
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
                created_at=ex.created_at,
            )
            for ex in examples
        ],
    )
