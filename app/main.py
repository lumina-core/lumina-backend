from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlmodel import SQLModel

from app.api.routes import users, products
from app.core.config import settings
from app.core.database import engine, ensure_database_exists


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting application initialization...")

    await ensure_database_exists()

    print("📋 Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    print("✓ All tables created successfully")

    yield

    print("🔌 Shutting down database connections...")
    await engine.dispose()


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(products.router, prefix="/api/v1/products", tags=["products"])


@app.get("/")
async def root():
    return {"message": "Welcome to Lumina Backend API", "version": settings.version}


@app.get("/health")
async def health():
    return {"status": "healthy"}
