"""
新闻RAG服务 - 基于本地Ollama embedding模型
使用 Chroma 存储向量数据到本地文件
"""

import os
from datetime import date
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from loguru import logger

load_dotenv()

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "qwen3-embedding")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")
VECTOR_COLLECTION = os.getenv("VECTOR_COLLECTION", "news_embeddings")


def get_sync_database_url() -> str:
    """获取同步数据库URL（将aiosqlite转换为sqlite）"""
    url = os.getenv("DATABASE_URL", "sqlite:///./data/lumina.db")
    return url.replace("+aiosqlite", "")


def get_embeddings() -> OllamaEmbeddings:
    """获取Ollama embedding服务"""
    return OllamaEmbeddings(model=EMBEDDING_MODEL)


def get_vector_store(embeddings: Optional[OllamaEmbeddings] = None) -> Chroma:
    """获取Chroma向量存储"""
    if embeddings is None:
        embeddings = get_embeddings()

    persist_dir = Path(CHROMA_PERSIST_DIR)
    persist_dir.mkdir(parents=True, exist_ok=True)

    return Chroma(
        collection_name=VECTOR_COLLECTION,
        embedding_function=embeddings,
        persist_directory=str(persist_dir),
    )


def date_to_int(d: date) -> int:
    """日期转为整数 YYYYMMDD 格式"""
    return d.year * 10000 + d.month * 100 + d.day


def fetch_news_articles(
    limit: int = 100,
    offset: int = 0,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> list[dict]:
    """从SQLite数据库获取新闻文章"""
    from sqlalchemy import create_engine, text

    engine = create_engine(get_sync_database_url())

    query = "SELECT id, news_date, title, url, content FROM news_articles WHERE 1=1"
    params = {}

    if start_date:
        query += " AND news_date >= :start_date"
        params["start_date"] = str(start_date)
    if end_date:
        query += " AND news_date <= :end_date"
        params["end_date"] = str(end_date)

    query += " ORDER BY news_date ASC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        return [dict(row._mapping) for row in result]


def count_news_articles(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> int:
    """统计日期范围内的新闻文章总数"""
    from sqlalchemy import create_engine, text

    engine = create_engine(get_sync_database_url())

    query = "SELECT COUNT(*) FROM news_articles WHERE 1=1"
    params = {}

    if start_date:
        query += " AND news_date >= :start_date"
        params["start_date"] = str(start_date)
    if end_date:
        query += " AND news_date <= :end_date"
        params["end_date"] = str(end_date)

    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        return result.scalar() or 0


def news_to_documents(articles: list[dict]) -> list[Document]:
    """将新闻文章转换为LangChain Document格式"""
    documents = []
    for article in articles:
        page_content = f"{article['title']}\n\n{article['content']}"
        news_date = article["news_date"]
        if isinstance(news_date, str):
            news_date = date.fromisoformat(news_date)
        metadata = {
            "news_id": article["id"],
            "title": article["title"],
            "news_date": str(news_date),
            "news_date_int": date_to_int(news_date),
            "url": article["url"],
        }
        documents.append(Document(page_content=page_content, metadata=metadata))
    return documents


def index_news(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    fetch_size: int = 100,
    embedding_batch_size: int = 10,
) -> list[str]:
    """索引新闻文章到向量数据库"""
    total_count = count_news_articles(start_date, end_date)
    logger.info(f"共有 {total_count} 篇文章待索引")

    if total_count == 0:
        logger.warning("无文章需要索引")
        return []

    embeddings = get_embeddings()
    vector_store = get_vector_store(embeddings)

    all_doc_ids = []
    offset = 0

    while True:
        articles = fetch_news_articles(
            limit=fetch_size,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
        )

        if not articles:
            break

        logger.info(f"获取到 {len(articles)} 篇文章")
        documents = news_to_documents(articles)

        for i in range(0, len(documents), embedding_batch_size):
            batch = documents[i : i + embedding_batch_size]
            doc_ids = vector_store.add_documents(batch)
            all_doc_ids.extend(doc_ids)
            logger.info(f"已索引 {len(all_doc_ids)}/{total_count}")

        offset += fetch_size

    logger.success(f"成功索引 {len(all_doc_ids)} 篇文章")
    return all_doc_ids


def search_news(
    query: str,
    k: int = 5,
    start_date_int: Optional[int] = None,
    end_date_int: Optional[int] = None,
    title_contains: Optional[str] = None,
    content_contains: Optional[str] = None,
) -> list[Document]:
    """语义搜索新闻，支持多种过滤条件"""
    vector_store = get_vector_store()

    where_filter = None
    where_conditions = []

    if start_date_int is not None:
        where_conditions.append({"news_date_int": {"$gte": start_date_int}})
    if end_date_int is not None:
        where_conditions.append({"news_date_int": {"$lte": end_date_int}})

    if len(where_conditions) == 1:
        where_filter = where_conditions[0]
    elif len(where_conditions) > 1:
        where_filter = {"$and": where_conditions}

    results = vector_store.similarity_search(
        query=query,
        k=k * 3 if (title_contains or content_contains) else k,
        filter=where_filter,
    )

    if title_contains or content_contains:
        filtered_results = []
        for doc in results:
            if (
                title_contains
                and title_contains.lower() not in doc.metadata.get("title", "").lower()
            ):
                continue
            if (
                content_contains
                and content_contains.lower() not in doc.page_content.lower()
            ):
                continue
            filtered_results.append(doc)
            if len(filtered_results) >= k:
                break
        return filtered_results

    return results[:k]


def clear_vector_store():
    """清空向量存储（用于重建索引）"""
    import shutil

    persist_dir = Path(CHROMA_PERSIST_DIR)
    if persist_dir.exists():
        shutil.rmtree(persist_dir)
        logger.info(f"已清空向量存储: {persist_dir}")


def int_to_date(d: int) -> date:
    """整数 YYYYMMDD 格式转为日期"""
    year = d // 10000
    month = (d % 10000) // 100
    day = d % 100
    return date(year, month, day)


def list_news(
    start_date_int: Optional[int] = None,
    end_date_int: Optional[int] = None,
    title_contains: Optional[str] = None,
    content_contains: Optional[str] = None,
    limit: int = 100,
) -> list[Document]:
    """
    按条件列出新闻（不使用语义搜索，直接从数据库查询）
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(get_sync_database_url())

    query = "SELECT id, news_date, title, url, content FROM news_articles WHERE 1=1"
    params = {}

    if start_date_int is not None:
        params["start_date"] = str(int_to_date(start_date_int))
        query += " AND news_date >= :start_date"
    if end_date_int is not None:
        params["end_date"] = str(int_to_date(end_date_int))
        query += " AND news_date <= :end_date"
    if title_contains:
        params["title_kw"] = f"%{title_contains}%"
        query += " AND title LIKE :title_kw"
    if content_contains:
        params["content_kw"] = f"%{content_contains}%"
        query += " AND content LIKE :content_kw"

    query += " ORDER BY news_date DESC LIMIT :limit"
    params["limit"] = limit

    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        articles = [dict(row._mapping) for row in result]

    return news_to_documents(articles)
