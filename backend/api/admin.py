from uuid import UUID
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.database.connection import get_db
from backend.database.models import (
    User, Store, Integration, ProductCache, Log,
    Subscription, Payment, SubscriptionStatus, GlobalProduct,
)
from backend.core.security import get_current_admin

router = APIRouter()


def _now():
    return datetime.now(timezone.utc)


@router.get("/stats")
async def get_platform_stats(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    total_users = await db.execute(select(func.count(User.id)))
    total_stores = await db.execute(select(func.count(Store.id)))
    total_products = await db.execute(select(func.count(ProductCache.id)))
    total_integrations = await db.execute(select(func.count(Integration.id)))

    # Check if global catalog needs to be created/populated (raw SQL avoids mapper issues)
    try:
        from sqlalchemy import text as _text
        global_count_res = await db.execute(_text("SELECT COUNT(*) FROM global_products"))
        global_count = global_count_res.scalar() or 0
    except Exception:
        global_count = -1  # table doesn't exist yet

    if global_count <= 0:
        from backend.database.backfill import backfill_global_products
        background_tasks.add_task(backfill_global_products)

    return {
        "total_users": total_users.scalar(),
        "total_stores": total_stores.scalar(),
        "total_products": total_products.scalar(),
        "total_integrations": total_integrations.scalar(),
        "global_catalog_count": global_count,
    }


@router.get("/users")
async def list_all_users(
    page: int = 1,
    limit: int = 50,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).offset((page - 1) * limit).limit(limit).order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    data = []
    for u in users:
        stores_count = await db.execute(
            select(func.count(Store.id)).where(Store.owner_id == u.id)
        )
        data.append({
            "id": str(u.id),
            "telegram_id": u.telegram_id,
            "username": u.telegram_username,
            "first_name": u.telegram_first_name,
            "is_active": u.is_active,
            "is_admin": u.is_admin,
            "stores_count": stores_count.scalar(),
            "created_at": u.created_at,
        })
    return data


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: UUID,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    stores_result = await db.execute(select(Store).where(Store.owner_id == user_id))
    stores = stores_result.scalars().all()

    return {
        "id": str(user.id),
        "telegram_id": user.telegram_id,
        "username": user.telegram_username,
        "first_name": user.telegram_first_name,
        "last_name": user.telegram_last_name,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
        "created_at": user.created_at,
        "stores": [
            {"id": str(s.id), "name": s.name, "is_active": s.is_active}
            for s in stores
        ],
    }


@router.patch("/users/{user_id}/toggle")
async def toggle_user(
    user_id: UUID,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя изменить свой аккаунт")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    user.is_active = not user.is_active
    return {"id": str(user.id), "is_active": user.is_active}


@router.get("/logs")
async def get_all_logs(
    level: str = None,
    page: int = 1,
    limit: int = 100,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(Log).order_by(Log.created_at.desc())
    if level:
        query = query.where(Log.level == level)
    query = query.offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        {
            "id": str(l.id),
            "user_id": str(l.user_id) if l.user_id else None,
            "store_id": str(l.store_id) if l.store_id else None,
            "level": l.level,
            "action": l.action,
            "message": l.message,
            "meta": l.meta,
            "created_at": l.created_at,
        }
        for l in logs
    ]


# ── Subscription management ──────────────────────────────────────────

def _sub_dict(sub: Subscription | None) -> dict:
    if not sub:
        return {"status": "none", "is_active": False}
    now = _now()
    if sub.status == SubscriptionStatus.trial:
        active = bool(sub.trial_ends_at and sub.trial_ends_at > now)
    elif sub.status == SubscriptionStatus.active:
        active = bool(sub.current_period_end and sub.current_period_end > now)
    else:
        active = False
    return {
        "id": str(sub.id),
        "status": sub.status,
        "is_active": active,
        "trial_ends_at": sub.trial_ends_at,
        "current_period_start": sub.current_period_start,
        "current_period_end": sub.current_period_end,
        "auto_renew": sub.auto_renew,
        "next_discount_percent": sub.next_discount_percent,
    }


@router.get("/subscriptions")
async def list_subscriptions(
    page: int = 1,
    limit: int = 50,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User, Subscription)
        .outerjoin(Subscription, Subscription.user_id == User.id)
        .order_by(User.created_at.desc())
        .offset((page - 1) * limit).limit(limit)
    )
    rows = result.all()
    return [
        {
            "user_id": str(u.id),
            "telegram_id": u.telegram_id,
            "username": u.telegram_username,
            "first_name": u.telegram_first_name,
            "subscription": _sub_dict(s),
        }
        for u, s in rows
    ]


class GrantSubRequest(BaseModel):
    days: Optional[int] = 30


@router.post("/subscriptions/{user_id}/grant")
async def grant_subscription(
    user_id: UUID,
    body: GrantSubRequest,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    sub = sub_result.scalar_one_or_none()

    now = _now()
    if sub:
        sub.status = SubscriptionStatus.active
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=body.days)
    else:
        sub = Subscription(
            user_id=user_id,
            status=SubscriptionStatus.active,
            trial_ends_at=now + timedelta(days=7),
            current_period_start=now,
            current_period_end=now + timedelta(days=body.days),
        )
        db.add(sub)

    await db.commit()
    return {"ok": True, "subscription": _sub_dict(sub)}


@router.delete("/subscriptions/{user_id}")
async def revoke_subscription(
    user_id: UUID,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Подписка не найдена")

    sub.status = SubscriptionStatus.cancelled
    sub.auto_renew = False
    await db.commit()
    return {"ok": True}


@router.post("/backfill-catalog")
async def trigger_backfill_catalog(
    current_user: User = Depends(get_current_admin),
):
    """Manually sync all existing products with barcodes into the global catalog."""
    from backend.database.backfill import backfill_global_products
    await backfill_global_products()
    return {"ok": True, "message": "Global catalog backfill completed"}


@router.get("/subscriptions/{user_id}")
async def get_user_subscription(
    user_id: UUID,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    sub = result.scalar_one_or_none()

    payments_result = await db.execute(
        select(Payment).where(Payment.user_id == user_id).order_by(Payment.created_at.desc()).limit(10)
    )
    payments = payments_result.scalars().all()

    return {
        "subscription": _sub_dict(sub),
        "payments": [
            {
                "id": str(p.id),
                "yookassa_payment_id": p.yookassa_payment_id,
                "amount": p.amount,
                "status": p.status,
                "created_at": p.created_at,
            }
            for p in payments
        ],
    }


@router.get("/products")
async def admin_list_products(
    search: str = "",
    page: int = 1,
    limit: int = 50,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import or_, String
    offset = (page - 1) * limit
    q = (
        select(ProductCache, Store, User)
        .join(Store, ProductCache.store_id == Store.id)
        .join(User, Store.owner_id == User.id)
        .where(ProductCache.is_active == True)
    )
    if search:
        q = q.where(
            or_(
                ProductCache.name.ilike(f"%{search}%"),
                ProductCache.barcode.ilike(f"%{search}%"),
                ProductCache.article.ilike(f"%{search}%"),
            )
        )
    total_res = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_res.scalar() or 0

    q = q.order_by(ProductCache.created_at.desc()).offset(offset).limit(limit)
    rows = (await db.execute(q)).all()

    return {
        "total": total,
        "page": page,
        "items": [
            {
                "id": str(p.id),
                "name": p.name,
                "barcode": p.barcode,
                "article": p.article,
                "category": p.category,
                "price": p.price,
                "quantity": p.quantity,
                "unit": p.unit,
                "store_id": str(p.store_id),
                "store_name": s.name,
                "owner": u.telegram_username or str(u.telegram_id),
                "created_at": p.created_at,
            }
            for p, s, u in rows
        ],
    }


class AdminBulkDeleteRequest(BaseModel):
    ids: list


@router.get("/products/{product_id}")
async def admin_get_product(
    product_id: UUID,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProductCache, Store, User)
        .join(Store, ProductCache.store_id == Store.id)
        .join(User, Store.owner_id == User.id)
        .where(ProductCache.id == product_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Товар не найден")
    p, s, u = row
    return {
        "id": str(p.id),
        "name": p.name,
        "barcode": p.barcode,
        "article": p.article,
        "category": p.category,
        "description": p.description,
        "price": p.price,
        "purchase_price": p.purchase_price,
        "quantity": p.quantity,
        "unit": p.unit,
        "onec_id": p.onec_id,
        "is_active": p.is_active,
        "created_at": p.created_at,
        "synced_at": p.synced_at,
        "store_id": str(p.store_id),
        "store_name": s.name,
        "owner_id": str(u.id),
        "owner": u.telegram_username or str(u.telegram_id),
        "owner_name": u.telegram_first_name or u.telegram_username or str(u.telegram_id),
    }


@router.delete("/products/bulk-delete")
async def admin_bulk_delete_products(
    body: AdminBulkDeleteRequest,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if not body.ids:
        return {"deleted": 0}
    from uuid import UUID as _UUID
    uuids = [_UUID(i) if isinstance(i, str) else i for i in body.ids]
    result = await db.execute(
        select(ProductCache).where(
            ProductCache.id.in_(uuids),
            ProductCache.is_active == True,
        )
    )
    products = result.scalars().all()
    for p in products:
        p.is_active = False
    await db.commit()
    return {"deleted": len(products)}
