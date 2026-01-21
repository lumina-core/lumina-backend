"""使用示例提交模型"""

from datetime import datetime, UTC
from typing import Optional, List

from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class ExampleSubmission(SQLModel, table=True):
    """使用示例提交表（审核队列）"""

    __tablename__ = "example_submissions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    chat_session_id: int = Field(foreign_key="chat_sessions.id", index=True)
    display_name: str = Field(max_length=50, description="提交者展示名称")

    # 状态: pending -> reviewing -> approved/rejected
    status: str = Field(
        default="pending",
        index=True,
        description="状态: pending/reviewing/approved/rejected",
    )

    # LLM 审核结果
    llm_score: Optional[float] = Field(default=None, description="质量评分 0-10")
    llm_category: Optional[str] = Field(
        default=None, max_length=50, description="LLM判定的分类"
    )
    llm_reason: Optional[str] = Field(default=None, description="审核理由/拒绝原因")

    submitted_at: datetime = Field(default_factory=utc_now)
    reviewed_at: Optional[datetime] = Field(default=None)


# ============ Request/Response Schemas ============


class ExampleSubmissionCreate(BaseModel):
    """提交示例请求"""

    chat_session_id: int
    display_name: str = PydanticField(
        max_length=50, description="展示名称（昵称或邮箱前缀）"
    )


class ExampleSubmissionRead(BaseModel):
    """提交记录响应"""

    id: int
    chat_session_id: int
    display_name: str
    status: str
    llm_score: Optional[float]
    llm_category: Optional[str]
    llm_reason: Optional[str]
    submitted_at: datetime
    reviewed_at: Optional[datetime]


class ExampleSubmissionListResponse(BaseModel):
    """提交记录列表响应"""

    total: int
    items: List[ExampleSubmissionRead]


class SubmitExampleResponse(BaseModel):
    """提交示例响应"""

    success: bool
    message: str
    submission_id: Optional[int] = None
