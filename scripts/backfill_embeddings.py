"""
Embedding 数据回刷脚本
- 增量刷新：通过 url 字段判断是否已索引，避免重复
- 清空功能：清理所有 embedding 数据

使用方式:
    # 增量刷新所有未索引的文章
    uv run -m scripts.backfill_embeddings backfill

    # 指定日期范围
    uv run -m scripts.backfill_embeddings backfill --start 2022-01-01 --end 2022-02-01

    # 清空所有 embedding 数据
    uv run -m scripts.backfill_embeddings clear

    # 查看统计信息
    uv run -m scripts.backfill_embeddings stats
"""

import argparse
from datetime import date

from loguru import logger

from app.agents.rag.news_rag import (
    count_news_articles,
    fetch_news_articles,
    get_embeddings,
    get_vector_store,
    news_to_documents,
    clear_vector_store,
)

logger.remove()
logger.add(
    sink=lambda msg: print(msg, end=""),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
    level="INFO",
)


def get_indexed_urls() -> set[str]:
    """从 Chroma 获取已索引的 url 集合"""
    vector_store = get_vector_store()
    collection = vector_store._collection
    results = collection.get(include=["metadatas"])
    if not results or not results.get("metadatas"):
        return set()
    return {m["url"] for m in results["metadatas"] if m.get("url")}


def get_indexed_count() -> int:
    """获取已索引的文档数量"""
    vector_store = get_vector_store()
    collection = vector_store._collection
    return collection.count()


def backfill_embeddings(
    start_date: date | None = None,
    end_date: date | None = None,
    fetch_size: int = 100,
    embedding_batch_size: int = 10,
) -> dict:
    """
    增量刷新 embedding，通过 url 去重
    返回统计信息 {added, skipped, failed}
    """
    stats = {"added": 0, "skipped": 0, "failed": 0}

    total_in_db = count_news_articles(start_date, end_date)
    logger.info(f"数据库中共有 {total_in_db} 篇文章")

    if total_in_db == 0:
        logger.warning("无文章需要处理")
        return stats

    logger.info("正在获取已索引的 URL 列表...")
    indexed_urls = get_indexed_urls()
    logger.info(f"Chroma 中已有 {len(indexed_urls)} 条记录")

    embeddings = get_embeddings()
    vector_store = get_vector_store(embeddings)

    offset = 0
    processed = 0

    try:
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
            skipped_count = len(articles) - len(new_articles)
            stats["skipped"] += skipped_count

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

            processed += len(articles)
            logger.info(
                f"进度: {processed}/{total_in_db} | "
                f"新增: {stats['added']} | 跳过: {stats['skipped']} | 失败: {stats['failed']}"
            )

            offset += fetch_size

    except KeyboardInterrupt:
        logger.warning("用户中断，已处理的数据已保存")

    logger.success(
        f"完成 - 新增: {stats['added']} | 跳过: {stats['skipped']} | 失败: {stats['failed']}"
    )
    return stats


def clear_embeddings(confirm: bool = False) -> bool:
    """
    清空所有 embedding 数据
    """
    count = get_indexed_count()
    logger.warning(f"即将清空 {count} 条 embedding 数据")

    if not confirm:
        response = input("确认清空所有数据? (yes/no): ")
        if response.lower() != "yes":
            logger.info("已取消")
            return False

    clear_vector_store()
    logger.success("已清空所有 embedding 数据")
    return True


def show_stats():
    """显示统计信息"""
    db_count = count_news_articles()
    indexed_count = get_indexed_count()
    indexed_urls = get_indexed_urls()

    logger.info(f"数据库文章总数: {db_count}")
    logger.info(f"已索引文档数: {indexed_count}")
    logger.info(f"已索引 URL 数: {len(indexed_urls)}")
    logger.info(f"未索引数量: {db_count - len(indexed_urls)}")


def parse_date(date_str: str) -> date:
    """解析日期字符串"""
    return date.fromisoformat(date_str)


def main():
    parser = argparse.ArgumentParser(description="Embedding 数据管理脚本")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # backfill 命令
    backfill_parser = subparsers.add_parser("backfill", help="增量刷新 embedding")
    backfill_parser.add_argument(
        "--start", type=parse_date, help="开始日期 (YYYY-MM-DD)"
    )
    backfill_parser.add_argument("--end", type=parse_date, help="结束日期 (YYYY-MM-DD)")
    backfill_parser.add_argument(
        "--fetch-size", type=int, default=100, help="每批获取数量"
    )
    backfill_parser.add_argument(
        "--batch-size", type=int, default=10, help="Embedding 批量大小"
    )

    # clear 命令
    clear_parser = subparsers.add_parser("clear", help="清空所有 embedding 数据")
    clear_parser.add_argument("-y", "--yes", action="store_true", help="跳过确认")

    # stats 命令
    subparsers.add_parser("stats", help="显示统计信息")

    args = parser.parse_args()

    if args.command == "backfill":
        backfill_embeddings(
            start_date=args.start,
            end_date=args.end,
            fetch_size=args.fetch_size,
            embedding_batch_size=args.batch_size,
        )
    elif args.command == "clear":
        clear_embeddings(confirm=args.yes)
    elif args.command == "stats":
        show_stats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
