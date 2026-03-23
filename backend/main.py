import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from backend.config import settings
from backend.database.connection import init_db
from backend.database.backfill import backfill_global_products
from backend.api import api_router
from backend.tasks.auto_renewal import renewal_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting 1С Helper API...")
    await init_db()
    logger.info("Database initialized")
    await backfill_global_products()
    task = asyncio.create_task(renewal_loop())
    yield
    task.cancel()
    logger.info("Shutting down 1С Helper API...")


app = FastAPI(
    title="1С Helper API",
    description="AI-powered inventory management for retail stores via Telegram",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "1С Helper API"}


@app.get("/")
async def root():
    return {"message": "1С Helper API", "version": "1.0.0"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development",
        log_level=settings.LOG_LEVEL.lower(),
    )
