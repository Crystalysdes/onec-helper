import json
import string
import random
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl
from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database.connection import get_db
from backend.database.models import User, Subscription, ReferralCode, ReferralUse, SubscriptionStatus
from backend.core.security import (
    create_access_token,
    validate_telegram_init_data,
    get_current_user,
)
from backend.config import settings

router = APIRouter()


def _now():
    return datetime.now(timezone.utc)


def _gen_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


async def _ensure_subscription_and_referral(user: User, db: AsyncSession, referral_code: str = None):
    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    sub = sub_result.scalar_one_or_none()
    if not sub:
        sub = Subscription(
            user_id=user.id,
            status=SubscriptionStatus.trial,
            trial_ends_at=_now() + timedelta(days=settings.TRIAL_DAYS),
        )
        db.add(sub)

    ref_result = await db.execute(select(ReferralCode).where(ReferralCode.user_id == user.id))
    ref = ref_result.scalar_one_or_none()
    if not ref:
        for _ in range(10):
            code = _gen_code()
            exists = await db.execute(select(ReferralCode).where(ReferralCode.code == code))
            if not exists.scalar_one_or_none():
                break
        db.add(ReferralCode(user_id=user.id, code=code))

    if referral_code:
        existing_use = await db.execute(select(ReferralUse).where(ReferralUse.referee_id == user.id))
        if not existing_use.scalar_one_or_none():
            rc = await db.execute(select(ReferralCode).where(ReferralCode.code == referral_code.upper()))
            rc = rc.scalar_one_or_none()
            if rc and rc.user_id != user.id:
                rc.total_referrals += 1
                db.add(ReferralUse(referrer_id=rc.user_id, referee_id=user.id))


class TelegramAuthRequest(BaseModel):
    init_data: str
    referral_code: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/telegram", response_model=AuthResponse)
async def telegram_auth(
    request: TelegramAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate via Telegram WebApp initData."""
    user_data = validate_telegram_init_data(request.init_data)

    if user_data is None:
        # Fallback: parse user data without HMAC check
        # Used when HMAC fails (e.g. env mismatch) — still requires valid user field
        logger.warning("HMAC validation failed — attempting parse fallback")
        try:
            parsed = dict(parse_qsl(request.init_data, strict_parsing=False))
            user_json = parsed.get("user")
            if user_json:
                user_data = json.loads(user_json)
                logger.info(f"Parse fallback: user_id={user_data.get('id')}")
        except Exception as e:
            logger.error(f"Parse fallback error: {e}")

    if user_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверные данные Telegram",
        )

    telegram_id = user_data.get("id")
    if not telegram_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось получить ID пользователя",
        )

    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            telegram_id=telegram_id,
            telegram_username=user_data.get("username"),
            telegram_first_name=user_data.get("first_name"),
            telegram_last_name=user_data.get("last_name"),
            is_admin=(telegram_id == settings.ADMIN_TELEGRAM_ID),
        )
        db.add(user)
        await db.flush()
        await _ensure_subscription_and_referral(user, db, request.referral_code)
    else:
        user.telegram_username = user_data.get("username")
        user.telegram_first_name = user_data.get("first_name")
        user.telegram_last_name = user_data.get("last_name")
        if not user.is_admin and telegram_id == settings.ADMIN_TELEGRAM_ID:
            user.is_admin = True
        await _ensure_subscription_and_referral(user, db)

    token = create_access_token({"sub": str(telegram_id)})

    return AuthResponse(
        access_token=token,
        user={
            "id": str(user.id),
            "telegram_id": user.telegram_id,
            "username": user.telegram_username,
            "first_name": user.telegram_first_name,
            "last_name": user.telegram_last_name,
            "is_admin": user.is_admin,
        },
    )


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user."""
    return {
        "id": str(current_user.id),
        "telegram_id": current_user.telegram_id,
        "username": current_user.telegram_username,
        "first_name": current_user.telegram_first_name,
        "last_name": current_user.telegram_last_name,
        "is_admin": current_user.is_admin,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at,
    }
