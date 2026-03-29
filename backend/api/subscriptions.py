import uuid
import string
import random
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from backend.database.connection import get_db
from backend.database.models import (
    User, Subscription, Payment, ReferralCode, ReferralUse,
    SubscriptionStatus, PaymentStatus,
)
from backend.core.security import get_current_user
from backend.config import settings
from backend.services import yookassa_service

router = APIRouter()

SUBSCRIPTION_PRICE = 2499.0
TRIAL_DAYS = 7
REFERRAL_DISCOUNT = 20   # %


# ── helpers ─────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_referral_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=8))


def _sub_dict(sub: Subscription) -> dict:
    now = _now()
    if sub.status == SubscriptionStatus.trial:
        active = sub.trial_ends_at and sub.trial_ends_at > now
    elif sub.status == SubscriptionStatus.active:
        active = sub.current_period_end and sub.current_period_end > now
    else:
        active = False

    days_left = None
    if sub.status == SubscriptionStatus.trial and sub.trial_ends_at:
        delta = sub.trial_ends_at - now
        days_left = max(0, delta.days)
    elif sub.status == SubscriptionStatus.active and sub.current_period_end:
        delta = sub.current_period_end - now
        days_left = max(0, delta.days)

    return {
        "status": sub.status,
        "is_active": active,
        "trial_ends_at": sub.trial_ends_at,
        "current_period_end": sub.current_period_end,
        "auto_renew": sub.auto_renew,
        "days_left": days_left,
        "next_discount_percent": sub.next_discount_percent,
    }


async def _get_or_create_sub(user: User, db: AsyncSession) -> Subscription:
    result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    sub = result.scalar_one_or_none()
    if not sub:
        sub = Subscription(
            user_id=user.id,
            status=SubscriptionStatus.trial,
            trial_ends_at=_now() + timedelta(days=TRIAL_DAYS),
        )
        db.add(sub)
        await db.flush()
    return sub


async def _get_or_create_referral(user: User, db: AsyncSession) -> ReferralCode:
    result = await db.execute(select(ReferralCode).where(ReferralCode.user_id == user.id))
    ref = result.scalar_one_or_none()
    if not ref:
        for _ in range(10):
            code = _gen_referral_code()
            exists = await db.execute(select(ReferralCode).where(ReferralCode.code == code))
            if not exists.scalar_one_or_none():
                break
        ref = ReferralCode(user_id=user.id, code=code)
        db.add(ref)
        await db.flush()
    return ref


# ── check subscription access ────────────────────────────────────────

async def require_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency: raise 402 if user has no valid subscription."""
    if current_user.is_admin:
        return current_user
    sub = await db.execute(select(Subscription).where(Subscription.user_id == current_user.id))
    sub = sub.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=402, detail="subscription_required")
    now = _now()
    if sub.status == SubscriptionStatus.trial:
        if not sub.trial_ends_at or sub.trial_ends_at <= now:
            raise HTTPException(status_code=402, detail="trial_expired")
    elif sub.status == SubscriptionStatus.active:
        if not sub.current_period_end or sub.current_period_end <= now:
            sub.status = SubscriptionStatus.expired
            raise HTTPException(status_code=402, detail="subscription_expired")
    else:
        raise HTTPException(status_code=402, detail="subscription_required")
    return current_user


# ── public endpoints ─────────────────────────────────────────────────

@router.get("/status")
async def get_subscription_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub = await _get_or_create_sub(current_user, db)
    ref = await _get_or_create_referral(current_user, db)
    await db.commit()
    return {
        **_sub_dict(sub),
        "referral_code": ref.code,
        "total_referrals": ref.total_referrals,
        "successful_referrals": ref.successful_referrals,
    }


@router.post("/create-payment")
async def create_payment(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub = await _get_or_create_sub(current_user, db)
    ref = await _get_or_create_referral(current_user, db)

    discount = sub.next_discount_percent or 0
    amount = yookassa_service.subscription_price(discount)
    description = f"Подписка 1C Helper — 1 месяц"
    if discount:
        description += f" (скидка {discount}%)"

    return_url = f"{settings.MINIAPP_URL}/?subscription=success"

    payment_data = await yookassa_service.create_payment(
        amount=amount,
        description=description,
        return_url=return_url,
        metadata={
            "user_id": str(current_user.id),
            "subscription_id": str(sub.id),
            "discount": discount,
        },
        save_payment_method=True,
        idempotency_key=f"sub-{sub.id}-{_now().strftime('%Y%m%d%H')}",
    )

    payment = Payment(
        subscription_id=sub.id,
        user_id=current_user.id,
        yookassa_payment_id=payment_data["id"],
        amount=amount,
        status=PaymentStatus.pending,
        confirmation_url=payment_data.get("confirmation", {}).get("confirmation_url"),
        description=description,
        metadata_json={"discount": discount},
    )
    db.add(payment)
    await db.commit()

    return {
        "payment_id": payment_data["id"],
        "confirmation_url": payment_data.get("confirmation", {}).get("confirmation_url"),
        "amount": amount,
        "discount": discount,
    }


@router.post("/webhook")
async def yookassa_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    event = body.get("event")
    obj = body.get("object", {})
    yookassa_payment_id = obj.get("id")

    if not yookassa_payment_id:
        return {"ok": True}

    result = await db.execute(
        select(Payment).where(Payment.yookassa_payment_id == yookassa_payment_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        logger.warning(f"Webhook: payment {yookassa_payment_id} not found")
        return {"ok": True}

    if event == "payment.succeeded":
        payment.status = PaymentStatus.succeeded

        result = await db.execute(select(Subscription).where(Subscription.id == payment.subscription_id))
        sub = result.scalar_one_or_none()
        if sub:
            now = _now()
            sub.status = SubscriptionStatus.active
            sub.current_period_start = now
            sub.current_period_end = now + timedelta(days=30)
            sub.next_discount_percent = 0

            saved_method = obj.get("payment_method", {})
            if saved_method.get("saved"):
                sub.yookassa_payment_method_id = saved_method.get("id")

            referral_result = await db.execute(
                select(ReferralUse).where(
                    ReferralUse.referee_id == sub.user_id,
                    ReferralUse.discount_granted == False,
                )
            )
            referral_use = referral_result.scalar_one_or_none()
            if referral_use:
                referral_use.discount_granted = True
                ref_code_result = await db.execute(
                    select(ReferralCode).where(ReferralCode.user_id == referral_use.referrer_id)
                )
                ref_code = ref_code_result.scalar_one_or_none()
                if ref_code:
                    ref_code.successful_referrals += 1

                referrer_sub_result = await db.execute(
                    select(Subscription).where(Subscription.user_id == referral_use.referrer_id)
                )
                referrer_sub = referrer_sub_result.scalar_one_or_none()
                if referrer_sub:
                    referrer_sub.next_discount_percent = max(
                        referrer_sub.next_discount_percent or 0, 20
                    )

                # Level 2: if the referrer was also referred by someone → 10% to level-2 referrer
                level2_result = await db.execute(
                    select(ReferralUse).where(
                        ReferralUse.referee_id == referral_use.referrer_id,
                    )
                )
                level2_use = level2_result.scalar_one_or_none()
                if level2_use:
                    l2_sub_result = await db.execute(
                        select(Subscription).where(Subscription.user_id == level2_use.referrer_id)
                    )
                    l2_sub = l2_sub_result.scalar_one_or_none()
                    if l2_sub:
                        l2_sub.next_discount_percent = max(
                            l2_sub.next_discount_percent or 0, 10
                        )
                    l2_ref_result = await db.execute(
                        select(ReferralCode).where(ReferralCode.user_id == level2_use.referrer_id)
                    )
                    l2_ref = l2_ref_result.scalar_one_or_none()
                    if l2_ref:
                        l2_ref.successful_referrals += 1

    elif event == "payment.canceled":
        payment.status = PaymentStatus.cancelled

    await db.commit()
    return {"ok": True}


@router.post("/toggle-auto-renew")
async def toggle_auto_renew(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub = await _get_or_create_sub(current_user, db)
    sub.auto_renew = not sub.auto_renew
    await db.commit()
    return {"auto_renew": sub.auto_renew}


@router.get("/referral")
async def get_referral_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ref = await _get_or_create_referral(current_user, db)
    await db.commit()
    bot_username = settings.BOT_USERNAME
    link = f"https://t.me/{bot_username}?start=ref_{ref.code}"

    uses_result = await db.execute(
        select(ReferralUse, User)
        .join(User, User.id == ReferralUse.referee_id)
        .where(ReferralUse.referrer_id == current_user.id)
        .order_by(ReferralUse.created_at.desc())
    )
    referrals = []
    for use, referred_user in uses_result.all():
        name = (
            referred_user.telegram_first_name
            or (f"@{referred_user.telegram_username}" if referred_user.telegram_username else None)
            or f"ID {referred_user.telegram_id}"
        )
        referrals.append({
            "name": name,
            "username": referred_user.telegram_username,
            "joined_at": use.created_at,
            "paid": use.discount_granted,
        })

    return {
        "code": ref.code,
        "link": link,
        "total_referrals": ref.total_referrals,
        "successful_referrals": ref.successful_referrals,
        "referrals": referrals,
    }


@router.post("/apply-referral")
async def apply_referral_code(
    code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(ReferralUse).where(ReferralUse.referee_id == current_user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Вы уже использовали реферальный код")

    ref_result = await db.execute(select(ReferralCode).where(ReferralCode.code == code.upper()))
    ref_code = ref_result.scalar_one_or_none()
    if not ref_code:
        raise HTTPException(status_code=404, detail="Реферальный код не найден")
    if ref_code.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя использовать собственный код")

    ref_code.total_referrals += 1
    use = ReferralUse(referrer_id=ref_code.user_id, referee_id=current_user.id)
    db.add(use)
    await db.commit()
    return {"ok": True, "message": "Реферальный код применён"}
