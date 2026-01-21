"""聊天历史模型"""

import secrets
from datetime import datetime, UTC
from typing import Optional, List

from pydantic import BaseModel
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """返回当前 UTC 时间（替代已废弃的 datetime.utcnow）"""
    return datetime.now(UTC)


class ChatSession(SQLModel, table=True):
    """聊天会话表"""

    __tablename__ = "chat_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    title: str = Field(max_length=200, description="会话标题")
    preview: Optional[str] = Field(default=None, max_length=500, description="预览内容")
    message_count: int = Field(default=0, description="消息数量")
    starred: bool = Field(default=False, description="是否收藏")

    # 分享相关字段
    is_public: bool = Field(default=False, description="是否公开分享")
    share_token: Optional[str] = Field(
        default=None, max_length=32, unique=True, index=True, description="分享令牌"
    )

    # 精选示例相关字段
    is_featured: bool = Field(default=False, index=True, description="是否为精选示例")
    featured_category: Optional[str] = Field(
        default=None, max_length=50, description="精选分类：投资视角/行业研究/企业决策/政策解读"
    )
    featured_order: int = Field(default=0, description="精选排序")

    # LangGraph thread_id，用于关联 checkpointer
    thread_id: Optional[str] = Field(
        default=None,
        max_length=64,
        unique=True,
        index=True,
        description="LangGraph会话ID",
    )

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @staticmethod
    def generate_share_token() -> str:
        """生成分享令牌"""
        return secrets.token_urlsafe(16)

    @staticmethod
    def generate_thread_id() -> str:
        """生成 LangGraph thread_id"""
        return secrets.token_hex(16)


class ChatMessage(SQLModel, table=True):
    """聊天消息表"""

    __tablename__ = "chat_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="chat_sessions.id", index=True)
    role: str = Field(max_length=20, description="角色: user/assistant")
    content: str = Field(description="消息内容")
    tool_calls: Optional[str] = Field(default=None, description="工具调用记录(JSON)")
    created_at: datetime = Field(default_factory=utc_now)


# ============ Request/Response Schemas ============


class ChatSessionCreate(BaseModel):
    """创建会话请求"""

    title: str
    preview: Optional[str] = None


class ChatSessionUpdate(BaseModel):
    """更新会话请求"""

    title: Optional[str] = None
    starred: Optional[bool] = None


class ChatSessionRead(BaseModel):
    """会话响应"""

    id: int
    title: str
    preview: Optional[str]
    message_count: int
    starred: bool
    is_public: bool = False
    share_token: Optional[str] = None
    share_url: Optional[str] = None  # 由 API 动态生成
    created_at: datetime
    updated_at: datetime


class ShareSessionResponse(BaseModel):
    """分享会话响应"""

    success: bool
    share_token: str
    share_url: str
    message: str


class SharedSessionRead(BaseModel):
    """公开分享的会话响应（只读）"""

    id: int
    title: str
    created_at: datetime
    messages: List["ChatMessageRead"]


class FeaturedExampleRead(BaseModel):
    """精选示例响应"""

    id: int
    title: str
    preview: Optional[str]
    category: Optional[str]
    share_token: str
    message_count: int
    created_at: datetime


class FeaturedExamplesResponse(BaseModel):
    """精选示例列表响应"""

    categories: List[str]
    examples: List[FeaturedExampleRead]


class ChatMessageCreate(BaseModel):
    """创建消息请求"""

    role: str
    content: str
    tool_calls: Optional[str] = None


class ChatMessageRead(BaseModel):
    """消息响应"""

    id: int
    session_id: int
    role: str
    content: str
    tool_calls: Optional[str]
    created_at: datetime


class ChatSessionListResponse(BaseModel):
    """会话列表响应"""

    total: int
    items: List[ChatSessionRead]


class ChatMessageListResponse(BaseModel):
    """消息列表响应"""

    total: int
    items: List[ChatMessageRead]
