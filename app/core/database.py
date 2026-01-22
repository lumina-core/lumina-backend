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
        from app.models.example import ExampleSubmission  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        logger.info("✓ 数据库表创建完成")

    except Exception as e:
        logger.error(f"创建数据库表失败: {e}")
        raise


def _check_table_exists(sync_conn, table_name: str) -> bool:
    """检查表是否存在（同步版本，供 run_sync 使用）"""
    from sqlalchemy import text

    result = sync_conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table_name},
    )
    return result.fetchone() is not None


def _get_table_columns(sync_conn, table_name: str) -> set:
    """获取表的所有列名（同步版本，供 run_sync 使用）"""
    from sqlalchemy import text

    result = sync_conn.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


async def auto_migrate_columns():
    """自动检查并添加缺失的列（仅适用于 SQLite）"""
    from sqlalchemy import text

    migrations = [
        # (表名, 列名, 列定义)
        ("chat_sessions", "is_featured", "BOOLEAN DEFAULT 0"),
        ("chat_sessions", "featured_category", "VARCHAR(50) DEFAULT NULL"),
        ("chat_sessions", "featured_order", "INTEGER DEFAULT 0"),
        ("chat_sessions", "featured_contributor", "VARCHAR(50) DEFAULT NULL"),
        # 邀请码功能新增字段
        ("invite_codes", "owner_id", "INTEGER DEFAULT NULL"),
        ("invite_codes", "use_count", "INTEGER DEFAULT 0"),
    ]

    async with engine.begin() as conn:
        for table, column, definition in migrations:
            existing_columns = await conn.run_sync(
                lambda c, t=table: _get_table_columns(c, t)
            )

            if column not in existing_columns:
                try:
                    await conn.run_sync(
                        lambda c, t=table, col=column, d=definition: c.execute(
                            text(f"ALTER TABLE {t} ADD COLUMN {col} {d}")
                        )
                    )
                    logger.info(f"✓ 自动添加列: {table}.{column}")
                except Exception as e:
                    logger.warning(f"添加列 {table}.{column} 失败: {e}")


async def auto_cleanup_deprecated():
    """自动清理已废弃的表和字段（仅适用于 SQLite）"""
    from sqlalchemy import text

    async with engine.begin() as conn:
        # 1. 删除已废弃的 credit_usage_logs 表（旧版邀请码使用记录）
        table_exists = await conn.run_sync(
            lambda c: _check_table_exists(c, "credit_usage_logs")
        )
        if table_exists:
            await conn.run_sync(
                lambda c: c.execute(text("DROP TABLE credit_usage_logs"))
            )
            logger.info("✓ 已删除废弃表: credit_usage_logs")

        # 2. 从 invite_codes 表删除 credits 字段（积分已统一到 user_credits）
        invite_table_exists = await conn.run_sync(
            lambda c: _check_table_exists(c, "invite_codes")
        )
        if not invite_table_exists:
            return

        invite_columns = await conn.run_sync(
            lambda c: _get_table_columns(c, "invite_codes")
        )
        if "credits" not in invite_columns:
            # credits 字段不存在，无需清理
            return

        logger.info("开始清理 invite_codes 表的 credits 字段...")

        # SQLite 不支持 DROP COLUMN，需要重建表
        # 步骤：创建新表 -> 复制数据 -> 删旧表 -> 重命名新表

        # 2.1 创建不含 credits 字段的新表
        await conn.run_sync(
            lambda c: c.execute(
                text("""
            CREATE TABLE invite_codes_new (
                code VARCHAR(32) PRIMARY KEY,
                owner_id INTEGER UNIQUE,
                use_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY (owner_id) REFERENCES users(id)
            )
        """)
            )
        )

        # 2.2 复制数据（只复制需要保留的字段）
        await conn.run_sync(
            lambda c: c.execute(
                text("""
            INSERT INTO invite_codes_new (code, owner_id, use_count, is_active, created_at, updated_at)
            SELECT code, owner_id, use_count, is_active, created_at, updated_at
            FROM invite_codes
        """)
            )
        )

        # 2.3 删除旧表
        await conn.run_sync(lambda c: c.execute(text("DROP TABLE invite_codes")))

        # 2.4 重命名新表
        await conn.run_sync(
            lambda c: c.execute(
                text("ALTER TABLE invite_codes_new RENAME TO invite_codes")
            )
        )

        # 2.5 重建索引
        await conn.run_sync(
            lambda c: c.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_invite_codes_owner_id ON invite_codes(owner_id)"
                )
            )
        )

        logger.info("✓ 已从 invite_codes 表删除废弃字段: credits")


async def init_database():
    """初始化数据库（检查数据库 + 创建表 + 自动迁移 + 清理废弃结构）"""
    logger.info("=" * 60)
    logger.info("开始初始化数据库")
    logger.info("=" * 60)

    await ensure_database_exists()
    await create_tables()
    await auto_migrate_columns()
    await auto_cleanup_deprecated()

    logger.info("=" * 60)
    logger.info("数据库初始化完成")
    logger.info("=" * 60)
