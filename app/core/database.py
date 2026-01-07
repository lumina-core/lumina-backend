from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel
import asyncpg
from loguru import logger

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    """获取数据库会话（依赖注入）"""
    async with async_session() as session:
        yield session


async def ensure_database_exists():
    """自动检查并创建数据库"""
    from urllib.parse import urlparse, urlunparse

    parsed_url = urlparse(settings.database_url)
    db_name = parsed_url.path.lstrip("/")

    postgres_url = urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            "/postgres",
            parsed_url.params,
            parsed_url.query,
            parsed_url.fragment,
        )
    )

    try:
        conn = await asyncpg.connect(
            postgres_url.replace("postgresql+asyncpg://", "postgresql://")
        )

        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )

        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            logger.info(f"✓ Database '{db_name}' created successfully")
        else:
            logger.info(f"✓ Database '{db_name}' already exists")

        await conn.close()

    except Exception as e:
        logger.error(f"Error ensuring database exists: {e}")
        raise


async def create_tables():
    """创建所有数据库表（基于 SQLModel 模型）"""
    try:
        logger.info("开始创建数据库表...")

        # 导入所有模型，确保 SQLModel 知道它们
        from app.models.user import User  # noqa: F401
        from app.models.news import NewsArticle  # noqa: F401
        from app.models.credit import CreditUsageLog, InviteCode  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        logger.info("✓ 数据库表创建完成")

    except Exception as e:
        logger.error(f"创建数据库表失败: {e}")
        raise


async def init_database():
    """初始化数据库（检查数据库 + 创建表）"""
    logger.info("=" * 60)
    logger.info("开始初始化数据库")
    logger.info("=" * 60)

    await ensure_database_exists()
    await create_tables()

    logger.info("=" * 60)
    logger.info("数据库初始化完成")
    logger.info("=" * 60)
