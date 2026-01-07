from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlmodel import SQLModel

from app.api.routes import users, products, tasks, news, chat, credits
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

app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(products.router, prefix="/api/v1/products", tags=["products"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["tasks"])
app.include_router(news.router, prefix="/api/v1/news", tags=["news"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(credits.router, prefix="/api/v1/credits", tags=["credits"])


@app.get("/")
async def root():
    return {"message": "Welcome to Lumina Backend API", "version": settings.version}


@app.get("/health")
async def health():
    return {"status": "healthy"}
