"""使用示例审核定时任务"""

from loguru import logger

from app.core.database import async_session
from app.core.scheduler import scheduler_manager
from app.services.example_review_service import ExampleReviewService


async def process_example_review_queue():
    """处理示例审核队列

    定时检查审核队列，使用 LLM 自动审核用户提交的示例。
    审核通过的示例会自动标记为精选并展示。
    """
    try:
        logger.info("=" * 60)
        logger.info("🔍 开始处理示例审核队列")
        logger.info("=" * 60)

        async with async_session() as session:
            review_service = ExampleReviewService(session)
            stats = await review_service.process_queue(limit=5)

        logger.info(
            f"✓ 审核任务完成 - 处理: {stats['processed']} | "
            f"通过: {stats['approved']} | 拒绝: {stats['rejected']} | 错误: {stats['errors']}"
        )
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ 示例审核任务失败: {str(e)}", exc_info=True)


def register_example_tasks():
    """注册示例审核相关的定时任务

    任务调度说明：
    - 每 10 分钟执行一次审核队列处理
    - 每次最多处理 5 个待审核示例
    """
    scheduler = scheduler_manager.scheduler

    scheduler.add_job(
        process_example_review_queue,
        trigger="interval",
        minutes=1,
        id="process_example_review_queue",
        name="示例审核队列处理",
        replace_existing=True,
    )
    logger.info("✓ 已注册任务：示例审核队列处理（每1分钟）")

    logger.info("=" * 60)
    logger.info("🎯 示例审核定时任务注册完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    import asyncio

    asyncio.run(process_example_review_queue())
