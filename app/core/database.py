from pathlib import Path

from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

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
    """确保SQLite数据库文件目录存在"""
    db_url = settings.database_url
    if db_url.startswith("sqlite"):
        db_path = db_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        if db_path.startswith("./"):
            db_path = db_path[2:]
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"✓ SQLite database path ready: {db_file}")


async def create_tables():
    """创建所有数据库表（基于 SQLModel 模型）"""
    try:
        logger.info("开始创建数据库表...")

        from app.models.auth import EmailVerification, InviteRelation, User  # noqa: F401
        from app.models.news import NewsArticle  # noqa: F401
        from app.models.chat import ChatSession, ChatMessage  # noqa: F401

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
