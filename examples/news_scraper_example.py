"""新闻爬虫服务使用示例

演示如何使用 NewsScraperService 抓取新闻数据
"""

import asyncio
from datetime import date

from loguru import logger

from app.services.news_scraper import news_scraper_service


async def example_fetch_news_list():
    """示例 1: 仅获取新闻列表（不包含详细内容）"""
    logger.info("示例 1: 获取新闻列表")

    target_date = date(2025, 11, 5)
    news_list = await news_scraper_service.fetch_news_list(target_date)

    logger.info(f"共找到 {len(news_list)} 条新闻")
    for idx, news in enumerate(news_list, start=1):
        logger.info(f"{idx}. {news['title']}")
        logger.info(f"   URL: {news['url']}")


async def example_fetch_single_news():
    """示例 2: 获取单条新闻的详细内容"""
    logger.info("\n示例 2: 获取单条新闻详情")

    target_date = date(2025, 11, 5)
    news_list = await news_scraper_service.fetch_news_list(target_date)

    if news_list:
        first_news = news_list[0]
        logger.info(f"正在获取: {first_news['title']}")

        content = await news_scraper_service.fetch_news_content(first_news["url"])
        logger.info(f"内容长度: {len(content)} 字符")
        logger.info(f"内容预览: {content[:200]}...")


async def example_scrape_daily_news():
    """示例 3: 完整抓取某日所有新闻（包含详细内容）"""
    logger.info("\n示例 3: 完整抓取每日新闻")

    target_date = date(2025, 11, 5)
    articles = await news_scraper_service.scrape_daily_news(target_date)

    logger.info(f"成功抓取 {len(articles)} 条新闻")

    for idx, article in enumerate(articles, start=1):
        logger.info(f"\n【新闻 {idx}】")
        logger.info(f"日期: {article.news_date}")
        logger.info(f"标题: {article.title}")
        logger.info(f"URL: {article.url}")
        logger.info(f"内容长度: {len(article.content)} 字符")


async def main():
    """主函数：依次执行所有示例"""
    try:
        # 示例 1: 获取新闻列表
        await example_fetch_news_list()

        # 示例 2: 获取单条新闻
        await example_fetch_single_news()

        # 示例 3: 完整抓取
        await example_scrape_daily_news()

    finally:
        # 清理资源
        await news_scraper_service.close()
        logger.info("\n资源已释放")


if __name__ == "__main__":
    asyncio.run(main())
