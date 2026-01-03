"""新闻相关的定时任务"""

from datetime import date, timedelta

from loguru import logger

from app.core.database import async_session
from app.core.scheduler import scheduler_manager
from app.services.news_service import NewsService


async def scrape_today_news():
    """定时任务：抓取今日新闻联播数据

    任务说明：
    - 每天自动抓取当天的新闻联播内容
    - 如果数据库已存在，则跳过
    - 自动处理异常，不影响其他任务
    """
    try:
        today = date.today()
        logger.info("=" * 60)
        logger.info(f"🤖 定时任务触发：抓取今日新闻（{today}）")
        logger.info("=" * 60)

        async with async_session() as session:
            news_service = NewsService(session)
            news_articles = await news_service.fetch_and_save_daily_news(today)

        logger.info(f"✓ 定时任务完成：成功处理 {len(news_articles)} 条新闻")

    except Exception as e:
        logger.error(f"❌ 定时任务失败：抓取今日新闻时出错 - {str(e)}", exc_info=True)


async def scrape_yesterday_news():
    """定时任务：抓取昨日新闻联播数据

    任务说明：
    - 补充抓取昨日的新闻数据（防止当天未成功抓取）
    - 如果数据库已存在，则跳过
    """
    try:
        yesterday = date.today() - timedelta(days=1)
        logger.info("=" * 60)
        logger.info(f"🤖 定时任务触发：抓取昨日新闻（{yesterday}）")
        logger.info("=" * 60)

        async with async_session() as session:
            news_service = NewsService(session)
            news_articles = await news_service.fetch_and_save_daily_news(yesterday)

        logger.info(f"✓ 定时任务完成：成功处理 {len(news_articles)} 条新闻")

    except Exception as e:
        logger.error(f"❌ 定时任务失败：抓取昨日新闻时出错 - {str(e)}", exc_info=True)


async def scrape_recent_week_news():
    """定时任务：批量抓取最近一周的新闻数据

    任务说明：
    - 每周执行一次，补充最近 7 天的新闻数据
    - 确保数据完整性
    """
    try:
        logger.info("=" * 60)
        logger.info("🤖 定时任务触发：批量抓取最近一周新闻")
        logger.info("=" * 60)

        today = date.today()
        success_count = 0
        skip_count = 0

        for i in range(7):
            target_date = today - timedelta(days=i)

            async with async_session() as session:
                news_service = NewsService(session)
                existing_count = await news_service.get_news_count_by_date(target_date)

                if existing_count > 0:
                    logger.info(
                        f"跳过 {target_date}：数据库已有 {existing_count} 条新闻"
                    )
                    skip_count += 1
                    continue

                news_articles = await news_service.fetch_and_save_daily_news(
                    target_date
                )
                if news_articles:
                    success_count += 1
                    logger.info(
                        f"✓ 成功抓取 {target_date}：{len(news_articles)} 条新闻"
                    )

        logger.info("=" * 60)
        logger.info(f"✓ 批量任务完成：成功 {success_count} 天，跳过 {skip_count} 天")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ 定时任务失败：批量抓取新闻时出错 - {str(e)}", exc_info=True)


def register_news_tasks():
    """注册所有新闻相关的定时任务

    任务调度说明：
    1. 每天 20:30 抓取今日新闻（新闻联播播出后）
    2. 每天 08:00 补充抓取昨日新闻（确保数据完整）
    3. 每周日 02:00 批量抓取最近一周数据（数据修复）
    """
    scheduler = scheduler_manager.scheduler

    # 任务 1：每天 20:30 抓取今日新闻
    scheduler.add_job(
        scrape_today_news,
        trigger="cron",
        hour=20,
        minute=30,
        id="scrape_today_news",
        name="抓取今日新闻联播",
        replace_existing=True,
    )
    logger.info("✓ 已注册任务：抓取今日新闻（每天 20:30）")

    # 任务 2：每天 08:00 补充抓取昨日新闻
    scheduler.add_job(
        scrape_yesterday_news,
        trigger="cron",
        hour=8,
        minute=0,
        id="scrape_yesterday_news",
        name="抓取昨日新闻联播",
        replace_existing=True,
    )
    logger.info("✓ 已注册任务：抓取昨日新闻（每天 08:00）")

    # 任务 3：每周日 02:00 批量抓取最近一周数据
    scheduler.add_job(
        scrape_recent_week_news,
        trigger="cron",
        day_of_week="sun",
        hour=2,
        minute=0,
        id="scrape_recent_week_news",
        name="批量抓取最近一周新闻",
        replace_existing=True,
    )
    logger.info("✓ 已注册任务：批量抓取最近一周新闻（每周日 02:00）")

    logger.info("=" * 60)
    logger.info("🎯 所有新闻定时任务注册完成")
    logger.info("=" * 60)
