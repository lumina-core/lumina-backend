"""新闻数据访问层"""

from datetime import date
from typing import List, Optional

from loguru import logger
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.news import NewsArticle, NewsArticleCreate, NewsArticleUpdate


class NewsRepository:
    """新闻数据仓储层

    职责：
    - 封装所有与新闻表相关的数据库操作
    - 提供 CRUD 接口
    - 处理查询逻辑
    """

    def __init__(self, session: AsyncSession):
        """初始化仓储

        Args:
            session: SQLModel 异步会话
        """
        self.session = session

    async def create(self, news_data: NewsArticleCreate) -> NewsArticle:
        """创建新闻记录

        Args:
            news_data: 新闻创建数据

        Returns:
            创建成功的新闻对象
        """
        news = NewsArticle.model_validate(news_data)
        self.session.add(news)
        await self.session.commit()
        await self.session.refresh(news)
        logger.debug(f"新闻已保存: ID={news.id}, 标题={news.title}")
        return news

    async def bulk_create(
        self, news_list: List[NewsArticleCreate]
    ) -> List[NewsArticle]:
        """批量创建新闻记录（跳过重复 URL）

        Args:
            news_list: 新闻列表

        Returns:
            成功创建的新闻列表
        """
        created_news = []
        for news_data in news_list:
            existing = await self.get_by_url(news_data.url)
            if existing:
                logger.debug(f"新闻已存在，跳过: {news_data.title}")
                continue

            news = NewsArticle.model_validate(news_data)
            self.session.add(news)
            created_news.append(news)

        if created_news:
            await self.session.commit()
            for news in created_news:
                await self.session.refresh(news)
            logger.info(f"批量保存完成: 新增 {len(created_news)} 条新闻")

        return created_news

    async def get_by_id(self, news_id: int) -> Optional[NewsArticle]:
        """根据 ID 获取新闻

        Args:
            news_id: 新闻 ID

        Returns:
            新闻对象或 None
        """
        return await self.session.get(NewsArticle, news_id)

    async def get_by_url(self, url: str) -> Optional[NewsArticle]:
        """根据 URL 获取新闻（检查是否已存在）

        Args:
            url: 新闻 URL

        Returns:
            新闻对象或 None
        """
        statement = select(NewsArticle).where(NewsArticle.url == url)
        result = await self.session.exec(statement)
        return result.first()

    async def get_by_date(self, news_date: date) -> List[NewsArticle]:
        """获取指定日期的所有新闻

        Args:
            news_date: 新闻日期

        Returns:
            新闻列表
        """
        statement = (
            select(NewsArticle)
            .where(NewsArticle.news_date == news_date)
            .order_by(col(NewsArticle.created_at))
        )
        result = await self.session.exec(statement)
        return list(result.all())

    async def get_date_range(
        self, start_date: date, end_date: date
    ) -> List[NewsArticle]:
        """获取日期范围内的新闻

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            新闻列表
        """
        statement = (
            select(NewsArticle)
            .where(NewsArticle.news_date >= start_date)
            .where(NewsArticle.news_date <= end_date)
            .order_by(col(NewsArticle.news_date).desc(), col(NewsArticle.created_at))
        )
        result = await self.session.exec(statement)
        return list(result.all())

    async def search_by_title(self, keyword: str) -> List[NewsArticle]:
        """按标题关键词搜索（简单模糊匹配）

        Args:
            keyword: 搜索关键词

        Returns:
            新闻列表
        """
        statement = (
            select(NewsArticle)
            .where(col(NewsArticle.title).ilike(f"%{keyword}%"))
            .order_by(col(NewsArticle.news_date).desc())
        )
        result = await self.session.exec(statement)
        return list(result.all())

    async def update(
        self, news_id: int, update_data: NewsArticleUpdate
    ) -> Optional[NewsArticle]:
        """更新新闻内容

        Args:
            news_id: 新闻 ID
            update_data: 更新数据

        Returns:
            更新后的新闻对象或 None
        """
        news = await self.get_by_id(news_id)
        if not news:
            logger.warning(f"新闻不存在: ID={news_id}")
            return None

        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(news, key, value)

        self.session.add(news)
        await self.session.commit()
        await self.session.refresh(news)
        logger.debug(f"新闻已更新: ID={news_id}")
        return news

    async def delete(self, news_id: int) -> bool:
        """删除新闻

        Args:
            news_id: 新闻 ID

        Returns:
            是否删除成功
        """
        news = await self.get_by_id(news_id)
        if not news:
            logger.warning(f"新闻不存在: ID={news_id}")
            return False

        await self.session.delete(news)
        await self.session.commit()
        logger.debug(f"新闻已删除: ID={news_id}")
        return True

    async def count_by_date(self, news_date: date) -> int:
        """统计指定日期的新闻数量

        Args:
            news_date: 新闻日期

        Returns:
            新闻数量
        """
        statement = select(NewsArticle).where(NewsArticle.news_date == news_date)
        result = await self.session.exec(statement)
        return len(list(result.all()))
