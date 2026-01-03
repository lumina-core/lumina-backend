"""新闻服务完整示例：爬虫 + 数据库存储

演示如何使用 NewsService 完成从爬取到存储的完整流程
"""

import asyncio
from datetime import date

from loguru import logger

from app.core.database import get_session, init_database
from app.services.news_service import NewsService


async def example_init_database():
    """示例 1: 初始化数据库（创建表）"""
    logger.info("示例 1: 初始化数据库")
    await init_database()


async def example_fetch_and_save():
    """示例 2: 爬取并保存新闻到数据库"""
    logger.info("\n示例 2: 爬取并保存新闻")

    target_date = date(2025, 11, 5)

    async for session in get_session():
        news_service = NewsService(session)

        # 第一次调用：会爬取并保存
        logger.info("第一次调用（会爬取）...")
        news_list = await news_service.fetch_and_save_daily_news(target_date)
        logger.info(f"获取到 {len(news_list)} 条新闻")

        # 第二次调用：直接从数据库读取
        logger.info("\n第二次调用（从缓存读取）...")
        cached_news = await news_service.fetch_and_save_daily_news(target_date)
        logger.info(f"从缓存获取 {len(cached_news)} 条新闻")


async def example_query_news():
    """示例 3: 查询数据库中的新闻"""
    logger.info("\n示例 3: 查询数据库")

    target_date = date(2025, 11, 5)

    async for session in get_session():
        news_service = NewsService(session)

        # 按日期查询
        news_list = await news_service.get_news_by_date(target_date)
        logger.info(f"查询到 {len(news_list)} 条新闻")

        # 显示前 3 ���
        for idx, news in enumerate(news_list[:3], start=1):
            logger.info(f"\n【新闻 {idx}】")
            logger.info(f"日期: {news.news_date}")
            logger.info(f"标题: {news.title}")
            logger.info(f"URL: {news.url}")
            logger.info(f"内容长度: {len(news.content)} 字符")
            logger.info(f"创建时间: {news.created_at}")


async def example_search_news():
    """示例 4: 搜索新闻"""
    logger.info("\n示例 4: 搜索新闻")

    keyword = "经济"

    async for session in get_session():
        news_service = NewsService(session)

        results = await news_service.search_by_title(keyword)
        logger.info(f"搜索关键词 '{keyword}'，找到 {len(results)} 条新闻")

        for idx, news in enumerate(results[:5], start=1):
            logger.info(f"{idx}. {news.title} ({news.news_date})")


async def example_date_range_query():
    """示例 5: 查询日期范围"""
    logger.info("\n示例 5: 日期范围查询")

    start_date = date(2025, 11, 1)
    end_date = date(2025, 11, 10)

    async for session in get_session():
        news_service = NewsService(session)

        news_list = await news_service.get_news_by_date_range(start_date, end_date)
        logger.info(f"日期范围 {start_date} ~ {end_date}，共 {len(news_list)} 条新闻")

        # 按日期统计
        from collections import defaultdict

        date_count = defaultdict(int)
        for news in news_list:
            date_count[news.news_date] += 1

        logger.info("\n每日新闻数量:")
        for news_date, count in sorted(date_count.items()):
            logger.info(f"  {news_date}: {count} 条")


async def main():
    """主函数：依次执行所有示例"""
    try:
        # 示例 1: 初始化数据库
        await example_init_database()

        # 示例 2: 爬取并保存
        await example_fetch_and_save()

        # 示例 3: 查询新闻
        await example_query_news()

        # 示例 4: 搜索新闻
        await example_search_news()

        # 示例 5: 日期范围查询
        await example_date_range_query()

    finally:
        # 清理爬虫资源
        from app.services.news_scraper import news_scraper_service

        await news_scraper_service.close()
        logger.info("\n✓ 资源已释放")


if __name__ == "__main__":
    asyncio.run(main())
