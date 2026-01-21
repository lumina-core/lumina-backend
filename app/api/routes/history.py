"""聊天历史路由"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session as get_db_session
from app.core.deps import get_current_user
from app.models.auth import User
from app.models.chat import (
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatSessionRead,
    ChatMessageCreate,
    ChatMessageRead,
    ChatSessionListResponse,
    ChatMessageListResponse,
    ShareSessionResponse,
    SharedSessionRead,
)
from app.services.chat_service import ChatService

router = APIRouter()


def _to_session_read(s, include_share: bool = False) -> ChatSessionRead:
    """转换会话模型为响应"""
    return ChatSessionRead(
        id=s.id,
        title=s.title,
        preview=s.preview,
        message_count=s.message_count,
        starred=s.starred,
        is_public=s.is_public,
        share_token=s.share_token if include_share and s.is_public else None,
        share_url=None,  # 前端自行拼接
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.get("", response_model=ChatSessionListResponse)
async def get_sessions(
    starred: bool = Query(False, description="仅显示收藏"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """获取聊天历史列表"""
    service = ChatService(session)
    sessions, total = await service.get_user_sessions(
        user.id, starred_only=starred, search=search, limit=limit, offset=offset
    )
    return ChatSessionListResponse(
        total=total,
        items=[_to_session_read(s, include_share=True) for s in sessions],
    )


@router.post("", response_model=ChatSessionRead)
async def create_session(
    data: ChatSessionCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """创建新的聊天会话"""
    service = ChatService(session)
    chat_session = await service.create_session(user.id, data)
    return _to_session_read(chat_session)


@router.get("/{session_id}", response_model=ChatSessionRead)
async def get_session(
    session_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """获取单个会话详情"""
    service = ChatService(session)
    chat_session = await service.get_session(session_id, user.id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return _to_session_read(chat_session, include_share=True)


@router.patch("/{session_id}", response_model=ChatSessionRead)
async def update_session(
    session_id: int,
    data: ChatSessionUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """更新会话（标题/收藏状态）"""
    service = ChatService(session)
    chat_session = await service.update_session(session_id, user.id, data)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return _to_session_read(chat_session, include_share=True)


@router.delete("/{session_id}")
async def delete_session(
    session_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """删除会话"""
    service = ChatService(session)
    deleted = await service.delete_session(session_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"success": True, "message": "删除成功"}


@router.get("/{session_id}/messages", response_model=ChatMessageListResponse)
async def get_messages(
    session_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """获取会话的所有消息"""
    service = ChatService(session)
    messages = await service.get_session_messages(session_id, user.id)
    return ChatMessageListResponse(
        total=len(messages),
        items=[
            ChatMessageRead(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                tool_calls=m.tool_calls,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.post("/{session_id}/messages", response_model=ChatMessageRead)
async def add_message(
    session_id: int,
    data: ChatMessageCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """向会话添加消息"""
    service = ChatService(session)
    message = await service.add_message(session_id, user.id, data)
    if not message:
        raise HTTPException(status_code=404, detail="会话不存在")
    return ChatMessageRead(
        id=message.id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        tool_calls=message.tool_calls,
        created_at=message.created_at,
    )


# ============ 分享相关接口 ============


@router.post("/{session_id}/share", response_model=ShareSessionResponse)
async def share_session(
    session_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """生成会话分享链接"""
    service = ChatService(session)
    chat_session = await service.share_session(session_id, user.id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return ShareSessionResponse(
        success=True,
        share_token=chat_session.share_token,
        share_url="",  # 前端自行拼接
        message="分享链接已生成",
    )


@router.delete("/{session_id}/share")
async def unshare_session(
    session_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """取消会话分享"""
    service = ChatService(session)
    chat_session = await service.unshare_session(session_id, user.id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"success": True, "message": "已取消分享"}


@router.get("/shared/{share_token}", response_model=SharedSessionRead)
async def get_shared_session(
    share_token: str,
    session: AsyncSession = Depends(get_db_session),
):
    """
    获取公开分享的会话（无需登录）

    任何人都可以通过分享链接查看会话内容
    """
    service = ChatService(session)
    chat_session, messages = await service.get_shared_session_messages(share_token)

    if not chat_session:
        raise HTTPException(status_code=404, detail="分享链接无效或已过期")

    return SharedSessionRead(
        id=chat_session.id,
        title=chat_session.title,
        created_at=chat_session.created_at,
        messages=[
            ChatMessageRead(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                tool_calls=m.tool_calls,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )
