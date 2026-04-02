import asyncio
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.config import settings

# ── Persistent log file ───────────────────────────────────────────────────────
_LOG_DIR = "/app/logs"
os.makedirs(_LOG_DIR, exist_ok=True)
logger.add(
    f"{_LOG_DIR}/app.log",
    rotation="50 MB",
    retention="14 days",
    compression="gz",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
    enqueue=True,
)
from backend.database.connection import init_db, engine
from backend.database.backfill import backfill_global_products
from backend.api import api_router
from backend.tasks.auto_renewal import renewal_loop
from backend.tasks.onec_sync import stock_alert_loop, auto_sync_loop, fast_stock_sync_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting 1С Helper API...")
    try:
        await asyncio.wait_for(init_db(), timeout=30)
        logger.info("Database initialized")
    except asyncio.TimeoutError:
        logger.error("init_db timed out — server starting without DB init")
    except Exception as e:
        logger.error(f"init_db failed: {e} — server starting anyway")
    try:
        await asyncio.wait_for(backfill_global_products(), timeout=20)
    except Exception as e:
        logger.warning(f"backfill skipped: {e}")
    # Pre-warm connection pool so first user requests don't create cold connections
    try:
        from backend.database.connection import engine
        async with engine.connect() as conn:
            await conn.execute(__import__('sqlalchemy').text("SELECT 1"))
        logger.info("DB connection pool warmed up")
    except Exception as e:
        logger.warning(f"Pool warm-up failed: {e}")
    task = asyncio.create_task(renewal_loop())
    stock_task = asyncio.create_task(stock_alert_loop())
    sync_task = asyncio.create_task(auto_sync_loop())
    fast_stock_task = asyncio.create_task(fast_stock_sync_loop())
    yield
    task.cancel()
    stock_task.cancel()
    sync_task.cancel()
    fast_stock_task.cancel()
    await engine.dispose()
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
    return {"status": "ok", "service": "1C Helper API"}


# ── Serve React SPA ───────────────────────────────────────────────────────────
_STATIC_DIR = "/app/static"
_INDEX = f"{_STATIC_DIR}/index.html"

if os.path.isdir(f"{_STATIC_DIR}/assets"):
    app.mount("/assets", StaticFiles(directory=f"{_STATIC_DIR}/assets"), name="assets")


@app.get("/vite.svg")
async def vite_svg():
    return FileResponse(f"{_STATIC_DIR}/vite.svg") if os.path.exists(f"{_STATIC_DIR}/vite.svg") else JSONResponse({}, 404)


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if os.path.exists(_INDEX):
        return FileResponse(_INDEX)
    return JSONResponse({"message": "1C Helper API", "version": "1.0.0"})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback as _tb
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}\n{''.join(_tb.format_tb(exc.__traceback__))}")
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
