import os
import re
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
    ReferralCode, ReferralUse,
)
from backend.core.security import get_current_admin
from backend.services import catalog_import as _ci

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
    total_products = await db.execute(select(func.count(ProductCache.id)).where(ProductCache.is_active == True))
    total_integrations = await db.execute(select(func.count(Integration.id)))

    # Check if global catalog needs to be created/populated (raw SQL avoids mapper issues)
    try:
        from sqlalchemy import text as _text
        global_count_res = await db.execute(_text("SELECT COUNT(*) FROM global_products WHERE is_excluded IS NOT TRUE"))
        global_count = global_count_res.scalar() or 0
    except Exception:
        global_count = -1  # table doesn't exist yet

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
    rows = (await db.execute(
        select(User, Subscription, ReferralCode)
        .outerjoin(Subscription, Subscription.user_id == User.id)
        .outerjoin(ReferralCode, ReferralCode.user_id == User.id)
        .order_by(User.created_at.desc())
        .offset((page - 1) * limit).limit(limit)
    )).all()

    data = []
    for u, sub, ref in rows:
        stores_count = (await db.execute(
            select(func.count(Store.id)).where(Store.owner_id == u.id)
        )).scalar()
        data.append({
            "id": str(u.id),
            "telegram_id": u.telegram_id,
            "username": u.telegram_username,
            "first_name": u.telegram_first_name,
            "is_active": u.is_active,
            "is_admin": u.is_admin,
            "stores_count": stores_count,
            "created_at": u.created_at,
            "subscription": _sub_dict(sub),
            "referral_code": ref.code if ref else None,
            "total_referrals": ref.total_referrals if ref else 0,
            "successful_referrals": ref.successful_referrals if ref else 0,
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

    ref_result = await db.execute(select(ReferralCode).where(ReferralCode.user_id == user_id))
    ref = ref_result.scalar_one_or_none()

    referred_by_result = await db.execute(
        select(ReferralUse, User)
        .join(User, User.id == ReferralUse.referrer_id)
        .where(ReferralUse.referee_id == user_id)
    )
    referred_by_row = referred_by_result.first()
    referred_by = None
    if referred_by_row:
        _, referrer_user = referred_by_row
        referred_by = (
            referrer_user.telegram_first_name
            or (f"@{referrer_user.telegram_username}" if referrer_user.telegram_username else None)
            or f"ID {referrer_user.telegram_id}"
        )

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
        "referral_code": ref.code if ref else None,
        "total_referrals": ref.total_referrals if ref else 0,
        "successful_referrals": ref.successful_referrals if ref else 0,
        "referred_by": referred_by,
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


@router.get("/app-logs")
async def get_app_logs(
    token: str = "",
    grep: str = "",
    lines: int = 200,
):
    """Read raw loguru log file. Protected by LOGS_TOKEN (no JWT needed).
    Query params:
      token — must match settings.LOGS_TOKEN
      grep  — optional substring filter (case-insensitive)
      lines — last N lines to return (default 200, max 2000)
    """
    from backend.config import settings
    from fastapi.responses import PlainTextResponse
    if not settings.LOGS_TOKEN or token != settings.LOGS_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    lines = min(max(1, lines), 2000)
    log_path = "/app/logs/app.log"
    if not os.path.exists(log_path):
        return PlainTextResponse("Log file not found yet.")
    try:
        with open(log_path, "r", errors="replace") as f:
            all_lines = f.readlines()
        if grep:
            all_lines = [l for l in all_lines if grep.lower() in l.lower()]
        tail = all_lines[-lines:]
        return PlainTextResponse("".join(tail))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    search: str = "",
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text as _text, or_
    q = select(User, Subscription).outerjoin(Subscription, Subscription.user_id == User.id)
    if search.strip():
        pattern = f"%{search.strip()}%"
        q = q.where(or_(
            User.telegram_username.ilike(pattern),
            User.telegram_first_name.ilike(pattern),
            User.telegram_last_name.ilike(pattern),
        ))
    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar() or 0
    q = q.order_by(User.created_at.desc()).offset((page - 1) * limit).limit(limit)
    rows = (await db.execute(q)).all()
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [
            {
                "user_id": str(u.id),
                "telegram_id": u.telegram_id,
                "username": u.telegram_username,
                "first_name": u.telegram_first_name,
                "subscription": _sub_dict(s),
            }
            for u, s in rows
        ],
    }


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


@router.get("/global-catalog")
async def admin_list_global_catalog(
    search: str = "",
    page: int = 1,
    limit: int = 50,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import or_
    offset = (page - 1) * limit
    q = select(GlobalProduct).where(
        (GlobalProduct.is_excluded == False) | (GlobalProduct.is_excluded.is_(None))
    )
    if search:
        q = q.where(
            or_(
                GlobalProduct.name.ilike(f"%{search}%"),
                GlobalProduct.barcode.ilike(f"%{search}%"),
                GlobalProduct.article.ilike(f"%{search}%"),
            )
        )
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(q.order_by(GlobalProduct.name).offset(offset).limit(limit))).scalars().all()
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
                "unit": p.unit,
            }
            for p in items
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


# ── Catalog import (DB-backed) ────────────────────────────────────────────────

@router.get("/catalog-file-check")
async def catalog_file_check(current_user: User = Depends(get_current_admin)):
    dir_ = _ci.CATALOG_DIR
    if not os.path.exists(dir_):
        return {"found": False, "file": None, "size_mb": 0}
    for fname in sorted(os.listdir(dir_)):
        if fname.endswith((".csv", ".zip")) and not fname.startswith("."):
            p = os.path.join(dir_, fname)
            return {"found": True, "file": fname, "size_mb": round(os.path.getsize(p) / 1024 / 1024, 1)}
    return {"found": False, "file": None, "size_mb": 0}


@router.get("/catalog-import-status")
async def catalog_import_status(current_user: User = Depends(get_current_admin)):
    job = await _ci.get_latest_job()
    if not job:
        return {"running": False, "done": False, "imported": 0, "skipped": 0, "stage": None, "error": None}
    return {
        "running": job["status"] == "running",
        "done":    job["status"] == "done",
        "error":   job["error_message"],
        "stage":   job["stage"],
        "imported": job["imported"],
        "skipped":  job["skipped"],
        "file":     job["file_name"],
    }


@router.post("/import-catalog")
async def import_russian_catalog(
    limit: int = 2_000_000,
    auto_clear: bool = False,
    current_user: User = Depends(get_current_admin),
):
    job = await _ci.get_latest_job()
    if job and job["status"] == "running":
        raise HTTPException(status_code=409, detail="Импорт уже запущен")
    if auto_clear:
        from sqlalchemy import text as _text
        from backend.database.connection import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await db.execute(_text("TRUNCATE TABLE global_products RESTART IDENTITY CASCADE"))
            await db.commit()
    job_id = await _ci.start_import(limit)
    return {"status": "started", "job_id": job_id}


@router.post("/ensure-catalog-index")
async def ensure_catalog_index(current_user: User = Depends(get_current_admin)):
    await _ci._ensure_trgm_index()
    return {"status": "ok"}


@router.post("/clean-garbled")
async def clean_garbled_catalog(current_user: User = Depends(get_current_admin)):
    """Delete encoding-corrupted (mojibake) records from global_products."""
    from backend.services.catalog_cleaner import _is_mojibake
    from sqlalchemy import text as _text
    from backend.database.connection import AsyncSessionLocal
    deleted = 0
    async with AsyncSessionLocal() as db:
        offset = 0
        batch_size = 5000
        while True:
            rows = (await db.execute(
                _text("SELECT id, name FROM global_products ORDER BY id OFFSET :off LIMIT :lim"),
                {"off": offset, "lim": batch_size}
            )).fetchall()
            if not rows:
                break
            bad_ids = [str(r[0]) for r in rows if _is_mojibake(r[1])]
            if bad_ids:
                await db.execute(
                    _text(f"DELETE FROM global_products WHERE id = ANY(:ids::uuid[])"),
                    {"ids": bad_ids}
                )
                await db.commit()
                deleted += len(bad_ids)
            offset += batch_size
    return {"status": "ok", "deleted": deleted}


@router.delete("/clear-catalog")
async def clear_catalog(current_user: User = Depends(get_current_admin)):
    """Hard-delete all global_products entries."""
    from sqlalchemy import text as _text
    from backend.database.connection import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(_text("SELECT COUNT(*) FROM global_products"))
        count = result.scalar()
        await db.execute(_text("DELETE FROM global_products"))
        await db.commit()
    return {"status": "cleared", "deleted": count}


@router.post("/dedup-catalog")
async def dedup_catalog(current_user: User = Depends(get_current_admin)):
    """
    Clean global_products:
    1. Remove article-based keys (article:...) — store-specific, not real EAN barcodes.
    2. Remove entries with very short names (< 3 chars after strip).
    3. Remove duplicate names — keep the entry with the best data (non-null price first, then oldest).
    """
    from sqlalchemy import text as _text
    from backend.database.connection import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        # Step 1: remove article-based keys
        r1 = await db.execute(_text("DELETE FROM global_products WHERE barcode LIKE 'article:%'"))
        removed_article = r1.rowcount

        # Step 2: remove too-short names
        r2 = await db.execute(_text("DELETE FROM global_products WHERE length(trim(name)) < 3"))
        removed_short = r2.rowcount

        # Step 3: remove duplicate names — keep best row per lower(name)
        # "Best" = has price (non-null) preferred, then by ctid (oldest physical row)
        r3 = await db.execute(_text("""
            DELETE FROM global_products
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY lower(name)
                               ORDER BY (price IS NOT NULL) DESC, id
                           ) AS rn
                    FROM global_products
                ) ranked
                WHERE rn > 1
            )
        """))
        removed_dupes = r3.rowcount

        await db.commit()
    return {
        "status": "ok",
        "removed_article_keys": removed_article,
        "removed_short_names": removed_short,
        "removed_duplicates": removed_dupes,
    }


@router.delete("/wipe-all")
async def wipe_all_products(current_user: User = Depends(get_current_admin)):
    """Nuclear option: hard-delete ALL rows from products_cache AND global_products."""
    from sqlalchemy import text as _text
    from backend.database.connection import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        pc_res = await db.execute(_text("SELECT COUNT(*) FROM products_cache"))
        pc_count = pc_res.scalar() or 0
        gp_res = await db.execute(_text("SELECT COUNT(*) FROM global_products"))
        gp_count = gp_res.scalar() or 0
        await db.execute(_text("DELETE FROM products_cache"))
        await db.execute(_text("DELETE FROM global_products"))
        await db.commit()
    return {"status": "wiped", "products_cache_deleted": pc_count, "global_products_deleted": gp_count}


class DownloadCatalogRequest(BaseModel):
    url: str
    filename: str  # e.g. "barcodes.csv" or "products.zip"


_download_status: dict = {"running": False, "done": False, "error": None, "filename": None, "size_mb": 0}


@router.get("/download-catalog-status")
async def download_catalog_status(current_user: User = Depends(get_current_admin)):
    return _download_status


@router.post("/download-catalog")
async def download_catalog(
    body: DownloadCatalogRequest,
    current_user: User = Depends(get_current_admin),
):
    if _download_status["running"]:
        raise HTTPException(status_code=409, detail="Скачивание уже идёт")
    filename = os.path.basename(body.filename.strip())
    if not filename or not filename.endswith((".csv", ".zip")):
        raise HTTPException(status_code=400, detail="Имя файла должно заканчиваться на .csv или .zip")
    _download_status.update({"running": True, "done": False, "error": None, "filename": filename, "size_mb": 0})
    _fire(_run_download(body.url.strip(), filename))
    return {"status": "started", "filename": filename}


async def _run_download(url: str, filename: str):
    import asyncio as _asyncio
    import aiohttp
    dest = os.path.join(_ci.CATALOG_DIR, filename)
    try:
        os.makedirs(_ci.CATALOG_DIR, exist_ok=True)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3600)) as resp:
                if resp.status != 200:
                    raise ValueError(f"HTTP {resp.status}")
                written = 0
                with open(dest, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1 << 20):  # 1MB
                        f.write(chunk)
                        written += len(chunk)
                        _download_status["size_mb"] = round(written / 1024 / 1024, 1)
        _download_status.update({"running": False, "done": True, "error": None, "size_mb": round(written / 1024 / 1024, 1)})
        logger.info(f"Downloaded {filename} → {dest} ({_download_status['size_mb']} MB)")
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        _download_status.update({"running": False, "done": True, "error": str(e)})
        if os.path.exists(dest):
            os.unlink(dest)


# ── AI batch cleanup ──────────────────────────────────────────────────────────
_ai_cleanup_status: dict = {"running": False, "processed": 0, "fixed": 0, "done": False, "error": None}
_bg_tasks: set = set()  # keeps task references alive (prevents GC)


def _fire(coro):
    import asyncio as _asyncio
    t = _asyncio.create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)
    return t


@router.get("/ai-cleanup-status")
async def ai_cleanup_status_endpoint(current_user: User = Depends(get_current_admin)):
    return _ai_cleanup_status


@router.post("/ai-cleanup-catalog")
async def ai_cleanup_catalog(
    current_user: User = Depends(get_current_admin),
):
    """Use AI to clean and normalize ALL suspicious GlobalProduct entries."""
    import asyncio
    if _ai_cleanup_status["running"]:
        raise HTTPException(status_code=409, detail="Очистка уже запущена")
    _ai_cleanup_status.update({"running": True, "processed": 0, "fixed": 0, "total": 0, "done": False, "error": None})
    _fire(_run_ai_cleanup())
    return {"status": "started"}


async def _run_ai_cleanup():
    import json as _json
    from sqlalchemy import text as _text
    from backend.database.connection import AsyncSessionLocal
    from backend.services.ai_service import AIService

    try:
        ai = AIService()
        processed = 0
        fixed = 0

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(_text(
                "SELECT id, name, category, unit FROM global_products "
                "WHERE name !~ '[а-яёА-ЯЁ]' OR length(trim(name)) < 5 "
                "ORDER BY id"
            ))).fetchall()

        if not rows:
            _ai_cleanup_status.update({"running": False, "done": True, "processed": 0, "fixed": 0, "total": 0})
            return

        _ai_cleanup_status["total"] = len(rows)
        CHUNK = 200
        for i in range(0, len(rows), CHUNK):
            chunk = rows[i:i + CHUNK]
            items = [{"id": str(r[0]), "name": r[1], "category": r[2] or "", "unit": r[3] or "шт"} for r in chunk]

            prompt = (
                "Нормализуй базу товаров для российского ритейла. "
                "Для каждого товара:\n"
                "1. Исправь/переведи название на русский, приведи в читаемый вид\n"
                "2. Категория на русском (если пустая или английская — заполни)\n"
                "3. Единица: шт/кг/г/л/мл/м/упак (определи из названия)\n"
                "4. Мусор (только коды, символы, бессмысленный набор) — верни name: null\n"
                "Верни ТОЛЬКО JSON массив без пояснений:\n"
                '[{"id":"...","name":"Название","category":"Категория","unit":"шт"}]\n\n'
                f"{_json.dumps(items, ensure_ascii=False)}"
            )

            try:
                raw = await ai._call([{"role": "user", "content": prompt}], max_tokens=8192, fast=True)
                # Extract JSON array
                match = re.search(r'\[.*\]', raw, re.DOTALL)
                if not match:
                    continue
                cleaned_items = _json.loads(match.group())
            except Exception as e:
                logger.warning(f"AI cleanup chunk error: {e}")
                continue

            async with AsyncSessionLocal() as db:
                for item in cleaned_items:
                    pid = item.get("id")
                    name = (item.get("name") or "").strip()
                    if not pid:
                        continue
                    if not name:
                        # Delete garbage
                        await db.execute(_text("DELETE FROM global_products WHERE id = :id"), {"id": pid})
                        fixed += 1
                    else:
                        await db.execute(_text(
                            "UPDATE global_products SET name=:name, category=:cat, unit=:unit WHERE id=:id"
                        ), {"id": pid, "name": name[:255], "cat": item.get("category") or None, "unit": item.get("unit") or "шт"})
                        fixed += 1
                await db.commit()

            processed += len(chunk)
            _ai_cleanup_status["processed"] = processed
            _ai_cleanup_status["fixed"] = fixed

        _ai_cleanup_status.update({"running": False, "done": True, "processed": processed, "fixed": fixed, "error": None})
        logger.info(f"AI cleanup done: processed={processed}, fixed={fixed}")

    except Exception as e:
        logger.error(f"AI cleanup error: {e}", exc_info=True)
        _ai_cleanup_status.update({"running": False, "done": True, "error": str(e)})


_PROXY_FILE = "/app/data/proxy.txt"


def _read_proxy_file() -> str:
    try:
        os.makedirs(os.path.dirname(_PROXY_FILE), exist_ok=True)
        if os.path.exists(_PROXY_FILE):
            return open(_PROXY_FILE).read().strip()
    except Exception:
        pass
    return ""


def _write_proxy_file(url: str):
    os.makedirs(os.path.dirname(_PROXY_FILE), exist_ok=True)
    with open(_PROXY_FILE, "w") as f:
        f.write(url.strip())


class ProxyConfigRequest(BaseModel):
    proxies: Optional[list] = None  # list of proxy URL strings
    proxy_url: Optional[str] = None  # legacy single-proxy compat


@router.get("/proxy-config")
async def get_proxy_config(current_user: User = Depends(get_current_admin)):
    """Return current proxy list (from file override or env)."""
    import json as _json
    from backend.config import settings
    raw = _read_proxy_file()
    if raw:
        try:
            data = _json.loads(raw)
            if isinstance(data, list):
                proxies = [p for p in data if p and str(p).strip()]
            else:
                proxies = [raw] if raw else []
        except Exception:
            proxies = [raw] if raw else []
        source = "file"
    else:
        env = (settings.ANTHROPIC_PROXY_URL or "").strip()
        proxies = [env] if env else []
        source = "env" if env else "none"
    return {"proxies": proxies, "source": source}


@router.post("/proxy-config")
async def set_proxy_config(
    body: ProxyConfigRequest,
    current_user: User = Depends(get_current_admin),
):
    """Save proxy list to file and reload AI service."""
    import json as _json
    # Accept both new list format and legacy single proxy_url
    if body.proxies is not None:
        proxies = [str(p).strip() for p in body.proxies if p and str(p).strip()]
    elif body.proxy_url is not None:
        proxies = [body.proxy_url.strip()] if body.proxy_url.strip() else []
    else:
        proxies = []
    _write_proxy_file(_json.dumps(proxies))
    try:
        from backend.services import ai_service as _ais
        _ais.reload_ai_service()
    except Exception as e:
        logger.warning(f"AI service reload after proxy change: {e}")
    return {"status": "saved", "proxies": proxies}


@router.post("/test-proxy")
async def test_proxy(
    body: ProxyConfigRequest,
    current_user: User = Depends(get_current_admin),
):
    """Test a proxy URL by making a minimal Anthropic API call through it."""
    import httpx
    from backend.config import settings
    proxy_url = (body.proxy_url or (body.proxies[0] if body.proxies else "") or "").strip()
    if not proxy_url:
        raise HTTPException(status_code=400, detail="Укажите URL прокси")
    try:
        if settings.OPENROUTER_API_KEY:
            # Test via OpenRouter: just check connectivity to the host
            async with httpx.AsyncClient(proxy=proxy_url, timeout=10) as client:
                r = await client.get("https://openrouter.ai/api/v1/models",
                                     headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"})
                return {"ok": r.status_code < 500, "status_code": r.status_code}
        else:
            async with httpx.AsyncClient(proxy=proxy_url, timeout=15.0) as http_client:
                r = await http_client.get(
                    "https://api.anthropic.com",
                    headers={"x-api-key": settings.ANTHROPIC_API_KEY},
                )
                return {"ok": r.status_code < 500, "status_code": r.status_code}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Прокси не работает: {e}")


@router.patch("/users/{user_id}/toggle-admin")
async def toggle_admin(
    user_id: UUID,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Grant or revoke admin rights for a user."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя изменить свои права")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.is_admin = not user.is_admin
    await db.commit()
    return {"id": str(user.id), "is_admin": user.is_admin}


@router.delete("/products/bulk-delete")
async def admin_bulk_delete_products(
    body: AdminBulkDeleteRequest,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if not body.ids:
        return {"deleted": 0}
    from uuid import UUID as _UUID
    from sqlalchemy import delete as _sa_delete
    uuids = []
    for i in body.ids:
        try:
            uuids.append(_UUID(str(i)))
        except (ValueError, AttributeError):
            pass
    if not uuids:
        return {"deleted": 0}
    from sqlalchemy import update as _sa_update
    result = await db.execute(
        _sa_update(GlobalProduct)
        .where(GlobalProduct.id.in_(uuids))
        .values(is_excluded=True)
        .returning(GlobalProduct.id)
    )
    deleted = len(result.fetchall())
    await db.commit()
    return {"deleted": deleted}
