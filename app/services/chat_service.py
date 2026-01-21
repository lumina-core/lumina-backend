"""聊天历史服务"""

from datetime import datetime
from typing import List, Optional

from sqlmodel import select, desc
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.chat import (
    ChatSession,
    ChatMessage,
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatMessageCreate,
)


class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(
        self, user_id: int, data: ChatSessionCreate
    ) -> ChatSession:
        """创建聊天会话，自动生成 thread_id"""
        chat_session = ChatSession(
            user_id=user_id,
            title=data.title,
            preview=data.preview,
            thread_id=ChatSession.generate_thread_id(),
        )
        self.session.add(chat_session)
        await self.session.commit()
        await self.session.refresh(chat_session)
        return chat_session

    async def get_user_sessions(
        self,
        user_id: int,
        starred_only: bool = False,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[ChatSession], int]:
        """获取用户的聊天会话列表"""
        query = select(ChatSession).where(ChatSession.user_id == user_id)

        if starred_only:
            query = query.where(ChatSession.starred.is_(True))

        if search:
            query = query.where(
                ChatSession.title.contains(search)
                | ChatSession.preview.contains(search)
            )

        # 计算总数
        count_query = select(ChatSession).where(ChatSession.user_id == user_id)
        if starred_only:
            count_query = count_query.where(ChatSession.starred.is_(True))
        if search:
            count_query = count_query.where(
                ChatSession.title.contains(search)
                | ChatSession.preview.contains(search)
            )
        result = await self.session.exec(count_query)
        total = len(result.all())

        # 获取分页数据
        query = query.order_by(desc(ChatSession.updated_at)).offset(offset).limit(limit)
        result = await self.session.exec(query)
        sessions = result.all()

        return list(sessions), total

    async def get_session(self, session_id: int, user_id: int) -> Optional[ChatSession]:
        """获取单个会话"""
        query = select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == user_id
        )
        result = await self.session.exec(query)
        return result.first()

    async def update_session(
        self, session_id: int, user_id: int, data: ChatSessionUpdate
    ) -> Optional[ChatSession]:
        """更新会话"""
        chat_session = await self.get_session(session_id, user_id)
        if not chat_session:
            return None

        if data.title is not None:
            chat_session.title = data.title
        if data.starred is not None:
            chat_session.starred = data.starred

        chat_session.updated_at = datetime.utcnow()
        self.session.add(chat_session)
        await self.session.commit()
        await self.session.refresh(chat_session)
        return chat_session

    async def delete_session(self, session_id: int, user_id: int) -> bool:
        """删除会话及其消息"""
        chat_session = await self.get_session(session_id, user_id)
        if not chat_session:
            return False

        # 删除所有消息
        messages_query = select(ChatMessage).where(ChatMessage.session_id == session_id)
        result = await self.session.exec(messages_query)
        for msg in result.all():
            await self.session.delete(msg)

        # 删除会话
        await self.session.delete(chat_session)
        await self.session.commit()
        return True

    async def add_message(
        self, session_id: int, user_id: int, data: ChatMessageCreate
    ) -> Optional[ChatMessage]:
        """添加消息到会话"""
        chat_session = await self.get_session(session_id, user_id)
        if not chat_session:
            return None

        message = ChatMessage(
            session_id=session_id,
            role=data.role,
            content=data.content,
            tool_calls=data.tool_calls,
        )
        self.session.add(message)

        # 更新会话统计
        chat_session.message_count += 1
        chat_session.updated_at = datetime.utcnow()
        if data.role == "user" and not chat_session.preview:
            chat_session.preview = data.content[:500]
        self.session.add(chat_session)

        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def get_session_messages(
        self, session_id: int, user_id: int
    ) -> List[ChatMessage]:
        """获取会话的所有消息"""
        chat_session = await self.get_session(session_id, user_id)
        if not chat_session:
            return []

        query = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        result = await self.session.exec(query)
        return list(result.all())

    # ============ 分享相关方法 ============

    async def share_session(
        self, session_id: int, user_id: int
    ) -> Optional[ChatSession]:
        """生成分享链接"""
        chat_session = await self.get_session(session_id, user_id)
        if not chat_session:
            return None

        # 如果已经有分享 token，直接返回
        if not chat_session.share_token:
            chat_session.share_token = ChatSession.generate_share_token()

        chat_session.is_public = True
        chat_session.updated_at = datetime.utcnow()
        self.session.add(chat_session)
        await self.session.commit()
        await self.session.refresh(chat_session)
        return chat_session

    async def unshare_session(
        self, session_id: int, user_id: int
    ) -> Optional[ChatSession]:
        """取消分享"""
        chat_session = await self.get_session(session_id, user_id)
        if not chat_session:
            return None

        chat_session.is_public = False
        chat_session.updated_at = datetime.utcnow()
        self.session.add(chat_session)
        await self.session.commit()
        await self.session.refresh(chat_session)
        return chat_session

    async def get_shared_session(self, share_token: str) -> Optional[ChatSession]:
        """通过分享 token 获取公开会话"""
        query = select(ChatSession).where(
            ChatSession.share_token == share_token,
            ChatSession.is_public.is_(True),
        )
        result = await self.session.exec(query)
        return result.first()

    async def get_shared_session_messages(
        self, share_token: str
    ) -> tuple[Optional[ChatSession], List[ChatMessage]]:
        """获取公开会话及其消息"""
        chat_session = await self.get_shared_session(share_token)
        if not chat_session:
            return None, []

        query = (
            select(ChatMessage)
            .where(ChatMessage.session_id == chat_session.id)
            .order_by(ChatMessage.created_at)
        )
        result = await self.session.exec(query)
        return chat_session, list(result.all())
