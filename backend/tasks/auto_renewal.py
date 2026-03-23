"""Background task: run every hour via lifespan to auto-renew subscriptions."""
import asyncio
from datetime import datetime, timedelta, timezone
from loguru import logger
from sqlalchemy import select
from backend.database.connection import AsyncSessionLocal
from backend.database.models import Subscription, Payment, SubscriptionStatus, PaymentStatus
from backend.services import yookassa_service


async def run_auto_renewal():
    """Charge users whose subscription ends within 24 hours and auto_renew=True."""
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=24)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.active,
                Subscription.auto_renew == True,
                Subscription.current_period_end <= window_end,
                Subscription.current_period_end > now,
                Subscription.yookassa_payment_method_id.isnot(None),
            )
        )
        subs = result.scalars().all()
        logger.info(f"Auto-renewal: {len(subs)} subscriptions to renew")

        for sub in subs:
            try:
                discount = sub.next_discount_percent or 0
                amount = yookassa_service.subscription_price(discount)
                idempotency_key = f"autorenewal-{sub.id}-{now.strftime('%Y%m%d')}"

                payment_data = await yookassa_service.create_auto_payment(
                    amount=amount,
                    payment_method_id=sub.yookassa_payment_method_id,
                    description=f"Автопродление подписки 1C Helper",
                    metadata={"user_id": str(sub.user_id), "subscription_id": str(sub.id), "auto": True},
                    idempotency_key=idempotency_key,
                )

                payment = Payment(
                    subscription_id=sub.id,
                    user_id=sub.user_id,
                    yookassa_payment_id=payment_data["id"],
                    amount=amount,
                    status=PaymentStatus.pending if payment_data["status"] == "pending" else PaymentStatus.succeeded,
                    description="Автопродление подписки",
                    metadata_json={"auto": True},
                )
                db.add(payment)

                if payment_data.get("status") == "succeeded":
                    sub.current_period_start = now
                    sub.current_period_end = now + timedelta(days=30)
                    sub.next_discount_percent = 0
                    logger.info(f"Auto-renewed subscription for user {sub.user_id}")

            except Exception as e:
                logger.error(f"Auto-renewal failed for sub {sub.id}: {e}")

        await db.commit()


async def renewal_loop():
    """Loop that runs auto-renewal every hour."""
    while True:
        try:
            await run_auto_renewal()
        except Exception as e:
            logger.error(f"Auto-renewal loop error: {e}")
        await asyncio.sleep(3600)
