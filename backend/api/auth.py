import string
import random
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel, EmailStr
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database.connection import get_db
from backend.database.models import User, Subscription, ReferralCode, ReferralUse, SubscriptionStatus
from backend.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
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


def _user_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name or "",
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "created_at": user.created_at,
    }


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    referral_code: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new account with email + password."""
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Пароль должен быть не менее 6 символов")

    existing = await db.execute(select(User).where(User.email == request.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")

    user = User(
        email=request.email.lower(),
        password_hash=hash_password(request.password),
        full_name=request.full_name.strip(),
        is_admin=(request.email.lower() == settings.ADMIN_EMAIL) if hasattr(settings, 'ADMIN_EMAIL') else False,
    )
    db.add(user)
    await db.flush()
    await _ensure_subscription_and_referral(user, db, request.referral_code)

    token = create_access_token({"sub": str(user.id)})
    logger.info(f"New user registered: {user.email}")
    return AuthResponse(access_token=token, user=_user_dict(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Login with email + password."""
    result = await db.execute(select(User).where(User.email == request.email.lower()))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")

    token = create_access_token({"sub": str(user.id)})
    return AuthResponse(access_token=token, user=_user_dict(user))


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user."""
    return _user_dict(current_user)
