"""
Periodic task: check 1C stock levels and send Telegram bot alerts for low-stock items.
Runs every STOCK_CHECK_INTERVAL_HOURS hours.
"""
import asyncio

import httpx
from loguru import logger
from sqlalchemy import select

from backend.config import settings
from backend.database.connection import AsyncSessionLocal
from backend.database.models import Integration, IntegrationStatus, Store, User
from backend.core.security import decrypt_password

STOCK_CHECK_INTERVAL_HOURS = 6
LOW_STOCK_THRESHOLD = 5.0
_TG_API = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"


async def _tg_send(chat_id: int, text: str):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(_TG_API, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    except Exception as e:
        logger.warning(f"Telegram send failed: {e}")


async def _check_and_notify():
    """Check all active integrations for low stock, notify owners via Telegram."""
    from backend.integrations.onec_integration import OneCClient

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

                client = OneCClient(
                    url=integration.onec_url,
                    username=integration.onec_username,
                    password=decrypt_password(integration.onec_password_encrypted),
                )
                success, balances = await client.get_stock_balances()
                if not success:
                    logger.warning(f"Stock check failed for integration {integration.id}")
                    continue

                low = [b for b in balances if b.get("quantity", 0) <= LOW_STOCK_THRESHOLD]
                if not low:
                    continue

                lines = "\n".join(
                    f"• {b.get('onec_id', '—')}: {b.get('quantity', 0)} шт."
                    for b in low[:20]
                )
                text = (
                    f"⚠️ <b>Низкий остаток товаров в 1С</b>\n"
                    f"Магазин: <b>{store.name}</b>\n\n"
                    f"{lines}\n\n"
                    f"Откройте приложение для подробностей."
                )
                await _tg_send(user.telegram_id, text)
                logger.info(f"Low-stock alert sent to user {user.telegram_id}: {len(low)} items")

            except Exception as e:
                logger.error(f"onec_sync error for integration {integration.id}: {e}")


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
