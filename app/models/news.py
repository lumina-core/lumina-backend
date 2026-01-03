from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class NewsArticleBase(SQLModel):
    """新闻文章基础字段"""

    news_date: date = Field(index=True, description="新闻日期")
    title: str = Field(max_length=500, description="新闻标题")
    url: str = Field(unique=True, index=True, max_length=1000, description="新闻URL")
    content: str = Field(description="新闻正文内容")


class NewsArticle(NewsArticleBase, table=True):
    """新闻文章表模型（数据库表）"""

    __tablename__ = "news_articles"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="创建时间", nullable=False
    )
    updated_at: Optional[datetime] = Field(default=None, description="更新时间")

    class Config:
        json_schema_extra = {
            "example": {
                "news_date": "2025-11-05",
                "title": "示例新闻标题",
                "url": "https://tv.cctv.com/2025/11/05/VIDExxxx.shtml",
                "content": "新闻正文内容...",
            }
        }


class NewsArticleCreate(NewsArticleBase):
    """创建新闻文章的请求模型"""

    pass


class NewsArticleRead(NewsArticleBase):
    """读取新闻文章的响应模型"""

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None


class NewsArticleUpdate(SQLModel):
    """更新新闻文章的请求模型（所有字段可选）"""

    title: Optional[str] = Field(default=None, max_length=500)
    content: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
