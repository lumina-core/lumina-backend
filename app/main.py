from fastapi import FastAPI
from app.api.routes import users, products
from app.core.config import settings

app = FastAPI(title=settings.app_name, version=settings.version)

app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(products.router, prefix="/api/v1/products", tags=["products"])


@app.get("/")
async def root():
    return {"message": "Welcome to Lumina Backend API", "version": settings.version}


@app.get("/health")
async def health():
    return {"status": "healthy"}
