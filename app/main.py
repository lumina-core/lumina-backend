from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlmodel import SQLModel

from app.api.routes import tasks, news, chat, credits, auth
from app.api.internal import invite_codes as internal_invite_codes
from app.api.internal import users as internal_users
from app.core.config import settings
from app.core.database import engine, ensure_database_exists
from app.core.scheduler import scheduler_manager
from app.tasks import register_news_tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting application initialization...")

    await ensure_database_exists()

    print("📋 Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    print("✓ All tables created successfully")

    # 启动定时任务调度器
    print("🕒 Initializing task scheduler...")
    register_news_tasks()
    scheduler_manager.start()
    scheduler_manager.print_jobs()
    print("✓ Task scheduler started successfully")

    yield

    # 关闭调度器
    print("🔌 Shutting down task scheduler...")
    scheduler_manager.shutdown(wait=True)

    print("🔌 Shutting down database connections...")
    await engine.dispose()


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

# 外部接口 - 需要 JWT 认证
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(news.router, prefix="/api/v1/news", tags=["news"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(credits.router, prefix="/api/v1/credits", tags=["credits"])

# 内部接口 - 不走 JWT，通过部署层面保护（如 nginx IP 白名单）
app.include_router(
    internal_invite_codes.router, prefix="/internal/invite-codes", tags=["internal"]
)
app.include_router(internal_users.router, prefix="/internal/users", tags=["internal"])
app.include_router(tasks.router, prefix="/internal/tasks", tags=["internal"])


@app.get("/")
async def root():
    return {"message": "Welcome to Lumina Backend API", "version": settings.version}


@app.get("/health")
async def health():
    return {"status": "healthy"}
