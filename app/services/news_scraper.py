"""新闻爬虫服务：从 CCTV 新闻联播抓取新闻数据"""

import asyncio
import random
from datetime import date
from typing import List, Optional

import httpx
from loguru import logger
from selectolax.parser import HTMLParser

from app.core.constants import USER_AGENT
from app.models.news import NewsArticle


class NewsScraperService:
    """新闻联播爬虫服务（单例模式）

    职责：
    - 抓取指定日期的新闻列表
    - 获取每条新闻的详细内容
    - 不涉及数据库操作，仅负责数据抓取
    """

    _instance: Optional["NewsScraperService"] = None

    BASE_URL = "https://tv.cctv.com/lm/xwlb/day/"
    REQUEST_DELAY_MIN = 1
    REQUEST_DELAY_MAX = 3
    REQUEST_TIMEOUT = 20.0
    DETAIL_TIMEOUT = 10.0

    def __new__(cls) -> "NewsScraperService":
        """单例模式：确保只有一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._http_client = None
        return cls._instance

    def __init__(self) -> None:
        """初始化爬虫服务"""
        if not hasattr(self, "_http_client"):
            self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端（单例模式）"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT},
                timeout=self.REQUEST_TIMEOUT,
            )
        return self._http_client

    async def close(self) -> None:
        """关闭 HTTP 客户端，释放资源"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
            logger.debug("HTTP 客户端已关闭")

    async def _add_random_delay(self) -> None:
        """添加随机延迟，避免请求过于频繁"""
        delay = random.uniform(self.REQUEST_DELAY_MIN, self.REQUEST_DELAY_MAX)
        await asyncio.sleep(delay)

    async def fetch_news_list(self, target_date: date) -> List[dict]:
        """获取指定日期的新闻列表

        Args:
            target_date: 目标日期

        Returns:
            新闻列表，每个元素包含 title 和 url

        Raises:
            httpx.HTTPError: HTTP 请求失败时抛出
        """
        date_str = target_date.strftime("%Y%m%d")
        daily_url = f"{self.BASE_URL}{date_str}.shtml"

        logger.info(f"开始抓取 {target_date} 的新闻列表")
        logger.debug(f"请求 URL: {daily_url}")

        await self._add_random_delay()

        client = await self._get_http_client()
        response = await client.get(daily_url)
        response.raise_for_status()

        news_list = []
        html_segments = response.text.split('    			<a href="')[2:]

        for segment in html_segments:
            try:
                news_url = segment.split('"')[0]
                news_title = segment.split('title="')[1].split('">')[0]
                news_list.append({"title": news_title, "url": news_url})
            except IndexError:
                logger.warning(f"解析新闻项失败，跳过: {segment[:50]}...")
                continue

        logger.info(f"成功获取 {len(news_list)} 条新闻")
        return news_list

    async def fetch_news_content(self, news_url: str) -> str:
        """获取单条新闻的详细内容

        Args:
            news_url: 新闻详情页 URL

        Returns:
            新闻正文内容，如果获取失败则返回空字符串
        """
        logger.debug(f"正在获取新闻内容: {news_url}")

        await self._add_random_delay()

        try:
            client = await self._get_http_client()
            response = await client.get(news_url, timeout=self.DETAIL_TIMEOUT)
            response.raise_for_status()

            parser = HTMLParser(response.text)
            content_element = parser.css_first("#content_area")

            if content_element:
                content = content_element.text(separator="\n", strip=True)
                logger.debug(f"成功提取内容，长度: {len(content)} 字符")
                return content
            else:
                logger.warning(f"未找到内容区域: {news_url}")
                return ""

        except httpx.HTTPError as e:
            logger.error(f"获取新闻内容失败 ({news_url}): {str(e)}")
            return ""

    async def scrape_daily_news(self, target_date: date) -> List[NewsArticle]:
        """抓取指定日期的完整新闻数据（包含详情）

        Args:
            target_date: 目标日期

        Returns:
            完整的新闻文章列表

        Raises:
            httpx.HTTPError: 抓取失败时抛出
        """
        logger.info("=" * 60)
        logger.info(f"开始抓取 {target_date} 的新闻数据")
        logger.info("=" * 60)

        news_list = await self.fetch_news_list(target_date)

        if not news_list:
            logger.warning("未获取到新闻列表")
            return []

        logger.info(f"开始获取 {len(news_list)} 条新闻的详细内容")

        news_articles = []
        total_count = len(news_list)

        for index, news_item in enumerate(news_list, start=1):
            logger.info(f"处理进度 [{index}/{total_count}]: {news_item['title']}")

            content = await self.fetch_news_content(news_item["url"])

            article = NewsArticle(
                news_date=target_date,
                title=news_item["title"],
                url=news_item["url"],
                content=content,
            )
            news_articles.append(article)

        logger.info("=" * 60)
        logger.info(f"完成抓取 {target_date} 的新闻数据，共 {len(news_articles)} 条")
        logger.info("=" * 60)

        return news_articles


# 创建全局单例实例
news_scraper_service = NewsScraperService()
