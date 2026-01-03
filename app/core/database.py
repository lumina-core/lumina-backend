from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import asyncpg

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
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
            print(f"✓ Database '{db_name}' created successfully")
        else:
            print(f"✓ Database '{db_name}' already exists")

        await conn.close()

    except Exception as e:
        print(f"Error ensuring database exists: {e}")
        raise
