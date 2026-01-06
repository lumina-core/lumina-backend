"""
新闻RAG服务 - 基于本地Ollama embedding模型
使用 langchain_postgres 存储向量数据到PostgreSQL
"""

import os
from datetime import date
from typing import Optional

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_postgres import PGEngine, PGVectorStore
from loguru import logger
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("+asyncpg", "+psycopg")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "qwen3-embedding")
VECTOR_TABLE = os.getenv("VECTOR_TABLE", "news_embeddings")
VECTOR_SIZE = int(os.getenv("VECTOR_SIZE", "4096"))


def get_pg_engine() -> PGEngine:
    """获取PGEngine实例"""
    return PGEngine.from_connection_string(url=DATABASE_URL)


def get_embeddings() -> OllamaEmbeddings:
    """获取Ollama embedding服务"""
    return OllamaEmbeddings(model=EMBEDDING_MODEL)


def ensure_vector_table(pg_engine: PGEngine, recreate: bool = False):
    """确保向量表存在，自动创建pgvector扩展和表"""
    sync_engine = create_engine(DATABASE_URL)
    with sync_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        if recreate:
            conn.execute(text(f"DROP TABLE IF EXISTS {VECTOR_TABLE}"))
            conn.commit()
            pg_engine.init_vectorstore_table(
                table_name=VECTOR_TABLE,
                vector_size=VECTOR_SIZE,
                overwrite_existing=False,
            )
            return

        result = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :table_name)"
            ),
            {"table_name": VECTOR_TABLE},
        )
        table_exists = result.scalar()

    if not table_exists:
        pg_engine.init_vectorstore_table(
            table_name=VECTOR_TABLE,
            vector_size=VECTOR_SIZE,
            overwrite_existing=False,
        )


def get_vector_store(
    pg_engine: PGEngine, embeddings: OllamaEmbeddings
) -> PGVectorStore:
    """获取向量存储"""
    ensure_vector_table(pg_engine)
    return PGVectorStore.create_sync(
        engine=pg_engine,
        table_name=VECTOR_TABLE,
        embedding_service=embeddings,
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
    """从数据库获取新闻文章"""
    engine = create_engine(DATABASE_URL)

    query = "SELECT id, news_date, title, url, content FROM news_articles WHERE 1=1"
    params = {}

    if start_date:
        query += " AND news_date >= :start_date"
        params["start_date"] = start_date
    if end_date:
        query += " AND news_date <= :end_date"
        params["end_date"] = end_date

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
    engine = create_engine(DATABASE_URL)

    query = "SELECT COUNT(*) FROM news_articles WHERE 1=1"
    params = {}

    if start_date:
        query += " AND news_date >= :start_date"
        params["start_date"] = start_date
    if end_date:
        query += " AND news_date <= :end_date"
        params["end_date"] = end_date

    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        return result.scalar() or 0


def news_to_documents(articles: list[dict]) -> list[Document]:
    """将新闻文章转换为LangChain Document格式"""
    documents = []
    for article in articles:
        page_content = f"{article['title']}\n\n{article['content']}"
        metadata = {
            "news_id": article["id"],
            "title": article["title"],
            "news_date": str(article["news_date"]),
            "news_date_int": date_to_int(article["news_date"]),
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

    pg_engine = get_pg_engine()
    embeddings = get_embeddings()
    vector_store = get_vector_store(pg_engine, embeddings)

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
    embeddings = get_embeddings()
    query_embedding = embeddings.embed_query(query)

    engine = create_engine(DATABASE_URL)

    sql = f"""
        SELECT 
            langchain_id,
            content,
            langchain_metadata,
            embedding <=> :embedding AS distance
        FROM {VECTOR_TABLE}
        WHERE 1=1
    """
    params: dict = {"embedding": str(query_embedding)}

    if start_date_int is not None:
        sql += " AND (langchain_metadata->>'news_date_int')::int >= :start_date"
        params["start_date"] = start_date_int
    if end_date_int is not None:
        sql += " AND (langchain_metadata->>'news_date_int')::int <= :end_date"
        params["end_date"] = end_date_int

    if title_contains:
        sql += " AND langchain_metadata->>'title' ILIKE :title_pattern"
        params["title_pattern"] = f"%{title_contains}%"

    if content_contains:
        sql += " AND content ILIKE :content_pattern"
        params["content_pattern"] = f"%{content_contains}%"

    sql += " ORDER BY distance ASC LIMIT :k"
    params["k"] = k

    with engine.connect() as conn:
        result = conn.execute(text(sql), params)
        rows = result.fetchall()

    documents = []
    for row in rows:
        metadata = row.langchain_metadata or {}
        documents.append(
            Document(
                page_content=row.content,
                metadata=metadata,
                id=str(row.langchain_id),
            )
        )

    return documents
