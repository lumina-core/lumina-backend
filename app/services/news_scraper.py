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

    @staticmethod
    def _is_full_broadcast(title: str) -> bool:
        """判断是否为完整版合集链接（非单条新闻，无正文内容）"""
        return title.startswith("《新闻联播》")

    @staticmethod
    def _parse_news_list_html(html: str) -> List[dict]:
        """从 HTML 解析新闻列表，兼容新旧两种页面格式

        早期格式（~2017-）：标题在 <div class="title"> 中，<a> 无 title 属性
        新格式（~2022+）：标题在 <a title="..."> 属性中
        """
        parser = HTMLParser(html)
        news_list: List[dict] = []
        seen_urls: set[str] = set()

        for li in parser.css("li"):
            a_tags = li.css("a")
            if not a_tags:
                continue

            href = ""
            title = ""

            for a in a_tags:
                h = a.attributes.get("href", "")
                if h and "cctv.com" in h:
                    href = h
                    title = a.attributes.get("title", "")
                    break

            if not href or href in seen_urls:
                continue

            if not title:
                title_div = li.css_first("div.title")
                if title_div:
                    title = title_div.text(strip=True)

            if not title or not href:
                continue

            seen_urls.add(href)
            news_list.append({"title": title, "url": href})

        return news_list

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

        all_news = self._parse_news_list_html(response.text)

        # 过滤掉完整版合集链接（无正文内容）
        news_list = [
            item for item in all_news if not self._is_full_broadcast(item["title"])
        ]

        filtered_count = len(all_news) - len(news_list)
        if filtered_count > 0:
            logger.debug(f"过滤掉 {filtered_count} 条完整版合集链接")

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
