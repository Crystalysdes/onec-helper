"""
Periodic tasks:
  1. auto_sync_loop  — every 30 min: pull new products + stock balances from 1C into bot
  2. stock_alert_loop — every 6 h: notify users about low-stock items via Telegram
"""
import asyncio
from uuid import UUID

import httpx
from loguru import logger
from sqlalchemy import select

from backend.config import settings
from backend.database.connection import AsyncSessionLocal
from backend.database.models import Integration, IntegrationStatus, ProductCache, Store, User
from backend.core.security import decrypt_password

SYNC_INTERVAL_SECONDS = 30
STOCK_CHECK_INTERVAL_HOURS = 6
LOW_STOCK_THRESHOLD = 5.0
_TG_API = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"


async def _tg_send(chat_id: int, text: str):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(_TG_API, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    except Exception as e:
        logger.warning(f"Telegram send failed: {e}")


async def _auto_sync_all():
    """Pull products + stock from all active 1C integrations into the bot."""
    from backend.api.stores import _run_sync_in_background

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Integration).where(Integration.status == IntegrationStatus.active)
        )
        integrations = result.scalars().all()

    for integration in integrations:
        try:
            await _run_sync_in_background(
                store_id=integration.store_id,
                integration_id=integration.id,
            )
        except Exception as e:
            logger.error(f"auto_sync error for integration {integration.id}: {e}")


async def _check_and_notify():
    """Check all active integrations for low stock, notify owners via Telegram."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Integration).where(Integration.status == IntegrationStatus.active)
        )
        integrations = result.scalars().all()

        for integration in integrations:
            try:
                store_result = await db.execute(
                    select(Store).where(Store.id == integration.store_id)
                )
                store = store_result.scalar_one_or_none()
                if not store:
                    continue

                user_result = await db.execute(
                    select(User).where(User.id == store.owner_id)
                )
                user = user_result.scalar_one_or_none()
                if not user:
                    continue

                # Fetch low-stock items using products_cache (has names + quantities)
                low_rows = (await db.execute(
                    select(ProductCache).where(
                        ProductCache.store_id == integration.store_id,
                        ProductCache.quantity <= LOW_STOCK_THRESHOLD,
                        ProductCache.quantity != None,
                        ProductCache.is_active == True,
                    )
                )).scalars().all()

                if not low_rows:
                    continue

                lines = "\n".join(
                    f"• <b>{p.name}</b>: {p.quantity or 0} {p.unit or 'шт'}"
                    for p in low_rows[:20]
                )
                text = (
                    f"⚠️ <b>Заканчиваются товары</b>\n"
                    f"Магазин: <b>{store.name}</b>\n\n"
                    f"{lines}\n\n"
                    f"Откройте приложение для подробностей."
                )
                await _tg_send(user.telegram_id, text)
                logger.info(f"Low-stock alert → user {user.telegram_id}: {len(low_rows)} items")

            except Exception as e:
                logger.error(f"onec_sync notify error for integration {integration.id}: {e}")


async def auto_sync_loop():
    """Background loop — sync products+stock from 1C every SYNC_INTERVAL_SECONDS."""
    logger.info(f"Auto-sync loop started (interval={SYNC_INTERVAL_SECONDS}s)")
    # First run after 30 s to let server fully start
    await asyncio.sleep(30)
    while True:
        logger.info("Running auto 1C sync...")
        try:
            await _auto_sync_all()
        except Exception as e:
            logger.error(f"auto_sync_loop error: {e}")
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


async def stock_alert_loop():
    """Background loop — runs every STOCK_CHECK_INTERVAL_HOURS hours."""
    logger.info(f"Stock alert loop started (interval={STOCK_CHECK_INTERVAL_HOURS}h)")
    while True:
        await asyncio.sleep(STOCK_CHECK_INTERVAL_HOURS * 3600)
        logger.info("Running 1C stock check...")
        try:
            await _check_and_notify()
        except Exception as e:
            logger.error(f"stock_alert_loop error: {e}")
