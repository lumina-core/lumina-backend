"""新闻业务服务：整合爬虫 + 存储"""

from datetime import date
from typing import List

from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.news import NewsArticle, NewsArticleCreate
from app.repositories.news_repository import NewsRepository
from app.services.news_scraper import news_scraper_service


class NewsService:
    """新闻业务服务

    职责：
    - 整合爬虫服务和数据存储
    - 提供高层业务逻辑
    - 处理缓存策略（优先从数据库读取）
    """

    def __init__(self, session: AsyncSession):
        """初始化新闻服务

        Args:
            session: 数据库会话
        """
        self.session = session
        self.repository = NewsRepository(session)

    async def fetch_and_save_daily_news(self, target_date: date) -> List[NewsArticle]:
        """抓取并保存指定日期的新闻

        工作流程：
        1. 检查数据库是否已有该日期的新闻
        2. 如有缓存，直接返回
        3. 如无缓存，爬取新闻并保存到数据库

        Args:
            target_date: 目标日期

        Returns:
            新闻列表
        """
        logger.info("=" * 60)
        logger.info(f"开始处理 {target_date} 的新闻数据")
        logger.info("=" * 60)

        # 1. 检查数据库缓存
        cached_news = await self.repository.get_by_date(target_date)
        if cached_news:
            logger.info(f"✓ 从数据库读取缓存: {len(cached_news)} 条新闻")
            return cached_news

        # 2. 缓存不存在，开始爬取
        logger.info("数据库无缓存，开始爬取新闻...")
        scraped_articles = await news_scraper_service.scrape_daily_news(target_date)

        if not scraped_articles:
            logger.warning("未爬取到任何新闻")
            return []

        # 3. 转换为数据库模型并保存
        create_data = [
            NewsArticleCreate(
                news_date=article.news_date,
                title=article.title,
                url=str(article.url),
                content=article.content,
            )
            for article in scraped_articles
        ]

        saved_news = await self.repository.bulk_create(create_data)

        logger.info("=" * 60)
        logger.info(
            f"✓ 完成处理 {target_date} 的新闻: 爬取 {len(scraped_articles)} 条，保存 {len(saved_news)} 条"
        )
        logger.info("=" * 60)

        # 4. 返回数据库中的最终结果
        return await self.repository.get_by_date(target_date)

    async def get_news_by_date(self, target_date: date) -> List[NewsArticle]:
        """仅从数据库获取指定日期的新闻（不爬取）

        Args:
            target_date: 目标日期

        Returns:
            新闻列表
        """
        return await self.repository.get_by_date(target_date)

    async def get_news_by_date_range(
        self, start_date: date, end_date: date
    ) -> List[NewsArticle]:
        """获取日期范围内的新闻

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            新闻列表
        """
        return await self.repository.get_date_range(start_date, end_date)

    async def search_by_title(self, keyword: str) -> List[NewsArticle]:
        """按标题搜索新闻

        Args:
            keyword: 搜索关键词

        Returns:
            新闻列表
        """
        return await self.repository.search_by_title(keyword)

    async def get_news_count_by_date(self, target_date: date) -> int:
        """获取指定日期的新闻数量

        Args:
            target_date: 目标日期

        Returns:
            新闻数量
        """
        return await self.repository.count_by_date(target_date)
