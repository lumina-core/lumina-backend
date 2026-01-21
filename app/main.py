from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger
from sqlmodel import SQLModel

from app.api.routes import tasks, news, chat, credits, auth, history, examples
from app.api.internal import invite_codes as internal_invite_codes
from app.api.internal import users as internal_users
from app.core.config import settings
from app.core.database import engine, ensure_database_exists
from app.core.exceptions import register_exception_handlers
from app.core.middleware import register_middlewares
from app.core.scheduler import scheduler_manager
from app.tasks import register_news_tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application initialization...")

    await ensure_database_exists()

    logger.info("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("All tables created successfully")

    # 启动定时任务调度器
    logger.info("Initializing task scheduler...")
    register_news_tasks()
    scheduler_manager.start()
    scheduler_manager.print_jobs()
    logger.info("Task scheduler started successfully")

    yield

    # 关闭调度器
    logger.info("Shutting down task scheduler...")
    scheduler_manager.shutdown(wait=True)

    logger.info("Shutting down database connections...")
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan,
    debug=settings.debug,
)

# 注册中间件和异常处理
register_middlewares(app)
register_exception_handlers(app)

# 外部接口 - 需要 JWT 认证
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(news.router, prefix="/api/v1/news", tags=["news"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(credits.router, prefix="/api/v1/credits", tags=["credits"])
app.include_router(history.router, prefix="/api/v1/history", tags=["history"])
app.include_router(examples.router, prefix="/api/v1/examples", tags=["examples"])

# 内部接口 - 不走 JWT，通过部署层面保护（如 nginx IP 白名单）
app.include_router(
    internal_invite_codes.router,
    prefix="/internal/v1/invite-codes",
    tags=["internal-invite-codes"],
)
app.include_router(
    internal_users.router,
    prefix="/internal/v1/users",
    tags=["internal-users"],
)
app.include_router(
    tasks.router,
    prefix="/internal/v1/tasks",
    tags=["internal-tasks"],
)


@app.get("/", summary="API 根路径", description="返回 API 基本信息")
async def root():
    return {"message": "Welcome to Lumina Backend API", "version": settings.version}


@app.get("/health", summary="健康检查", description="用于负载均衡器和监控的健康检查端点")
async def health():
    return {"status": "healthy"}
