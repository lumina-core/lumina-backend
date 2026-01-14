"""新闻相关的定时任务"""

from datetime import date, timedelta

from loguru import logger

from app.core.database import async_session
from app.core.scheduler import scheduler_manager
from app.services.news_service import NewsService


def backfill_embeddings_for_week(start_date: date, end_date: date) -> dict:
    """补充指定日期范围的 embedding（复用 backfill_embeddings 逻辑）"""
    from app.agents.rag.news_rag import (
        count_news_articles,
        fetch_news_articles,
        get_embeddings,
        get_vector_store,
        news_to_documents,
    )

    stats = {"added": 0, "skipped": 0, "failed": 0}

    total_in_db = count_news_articles(start_date, end_date)
    if total_in_db == 0:
        logger.info("该日期范围内无文章需要处理 embedding")
        return stats

    vector_store = get_vector_store()
    collection = vector_store._collection
    results = collection.get(include=["metadatas"])
    indexed_urls = set()
    if results and results.get("metadatas"):
        indexed_urls = {m["url"] for m in results["metadatas"] if m.get("url")}

    logger.info(f"数据库中有 {total_in_db} 篇文章，已索引 {len(indexed_urls)} 条")

    embeddings = get_embeddings()
    vector_store = get_vector_store(embeddings)

    offset = 0
    fetch_size = 100
    embedding_batch_size = 10

    while True:
        articles = fetch_news_articles(
            limit=fetch_size,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
        )
        if not articles:
            break

        new_articles = [a for a in articles if a["url"] not in indexed_urls]
        stats["skipped"] += len(articles) - len(new_articles)

        if new_articles:
            documents = news_to_documents(new_articles)
            for i in range(0, len(documents), embedding_batch_size):
                batch = documents[i : i + embedding_batch_size]
                try:
                    vector_store.add_documents(batch)
                    stats["added"] += len(batch)
                    for doc in batch:
                        indexed_urls.add(doc.metadata["url"])
                except Exception as e:
                    logger.error(f"索引失败: {e}")
                    stats["failed"] += len(batch)

        offset += fetch_size

    return stats


async def daily_maintenance_task():
    """每日维护任务：检测并补充过去一周的新闻数据和 embedding

    任务说明：
    - 每天 05:00 自动执行
    - 检查过去 7 天的新闻数据，缺失则补充
    - 检查 embedding 索引，缺失则补充
    - 实现 0 人工维护成本
    """
    try:
        logger.info("=" * 60)
        logger.info("🤖 每日维护任务触发")
        logger.info("=" * 60)

        today = date.today()
        start_date = today - timedelta(days=7)

        # 第一步：补充新闻数据
        logger.info("📰 步骤 1/2：检查并补充新闻数据")
        news_stats = {"success": 0, "skipped": 0, "failed": 0}

        for i in range(7):
            target_date = today - timedelta(days=i)
            async with async_session() as session:
                news_service = NewsService(session)
                existing_count = await news_service.get_news_count_by_date(target_date)

                if existing_count > 0:
                    logger.info(f"  {target_date} 已有 {existing_count} 条，跳过")
                    news_stats["skipped"] += 1
                else:
                    try:
                        articles = await news_service.fetch_and_save_daily_news(
                            target_date
                        )
                        logger.info(f"  {target_date} 采集 {len(articles)} 条")
                        news_stats["success"] += 1
                    except Exception as e:
                        logger.error(f"  {target_date} 失败: {e}")
                        news_stats["failed"] += 1

        logger.info(
            f"新闻补充完成 - 成功: {news_stats['success']} | "
            f"跳过: {news_stats['skipped']} | 失败: {news_stats['failed']}"
        )

        # 第二步：补充 embedding
        logger.info("🔍 步骤 2/2：检查并补充 embedding")
        embed_stats = backfill_embeddings_for_week(start_date, today)
        logger.info(
            f"Embedding 补充完成 - 新增: {embed_stats['added']} | "
            f"跳过: {embed_stats['skipped']} | 失败: {embed_stats['failed']}"
        )

        logger.info("=" * 60)
        logger.info("✓ 每日维护任务完成")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ 每日维护任务失败: {str(e)}", exc_info=True)


def register_news_tasks():
    """注册新闻相关的定时任务

    任务调度说明：
    - 每天 05:00 执行每日维护任务
    - 自动检测并补充过去一周的新闻数据和 embedding
    """
    scheduler = scheduler_manager.scheduler

    scheduler.add_job(
        daily_maintenance_task,
        trigger="cron",
        hour=5,
        minute=0,
        id="daily_maintenance_task",
        name="每日维护任务（新闻+Embedding）",
        replace_existing=True,
    )
    logger.info("✓ 已注册任务：每日维护任务（每天 05:00）")

    logger.info("=" * 60)
    logger.info("🎯 新闻定时任务注册完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    import asyncio

    asyncio.run(daily_maintenance_task())
