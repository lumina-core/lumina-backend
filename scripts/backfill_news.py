import asyncio
from datetime import date, timedelta

from loguru import logger

from app.core.database import async_session, ensure_database_exists
from app.services.news_service import NewsService
from app.services.news_scraper import news_scraper_service

# ========== 配置区域 ==========
START_DATE = date(2022, 1, 1)
END_DATE = date(2023, 1, 1)
# =============================

logger.remove()
logger.add(
    sink=lambda msg: print(msg, end=""),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
    level="INFO",
)


async def backfill(start_date: date, end_date: date):
    logger.info(f"补采范围: {start_date} 至 {end_date}")
    await ensure_database_exists()

    stats = {"success": 0, "skipped": 0, "failed": 0}
    current = start_date

    try:
        while current <= end_date:
            async with async_session() as session:
                service = NewsService(session)
                count = await service.get_news_count_by_date(current)

                if count > 0:
                    logger.info(f"{current} 已有 {count} 条，跳过")
                    stats["skipped"] += 1
                else:
                    try:
                        articles = await service.fetch_and_save_daily_news(current)
                        logger.info(f"{current} 采集并保存 {len(articles)} 条")
                        stats["success"] += 1
                    except Exception as e:
                        logger.error(f"{current} 失败: {e}")
                        stats["failed"] += 1

            current += timedelta(days=1)

    except KeyboardInterrupt:
        logger.warning("中断，已完成的数据已保存")
    finally:
        await news_scraper_service.close()

    logger.info(
        f"完成 - 成功: {stats['success']} | 跳过: {stats['skipped']} | 失败: {stats['failed']}"
    )


if __name__ == "__main__":
    asyncio.run(backfill(START_DATE, END_DATE))
