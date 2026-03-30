import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from loguru import logger

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update as sa_update

from backend.database.connection import get_db
from backend.database.models import User, Store, ProductCache, Integration, IntegrationStatus, Log, LogLevel, GlobalProduct
from backend.core.security import get_current_user

router = APIRouter()

UPLOAD_DIR = "/app/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class ProductCreate(BaseModel):
    store_id: str
    name: str
    price: Optional[float] = None
    purchase_price: Optional[float] = None
    barcode: Optional[str] = None
    article: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[float] = 0
    unit: Optional[str] = "шт"
    description: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    purchase_price: Optional[float] = None
    barcode: Optional[str] = None
    article: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


def _compress_image(image_bytes: bytes, max_px: int = 800) -> bytes:
    """Resize image so the longest side is at most max_px, then re-encode as JPEG quality=85."""
    try:
        import io as _io
        from PIL import Image as _Img
        img = _Img.open(_io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        if max(w, h) > max_px:
            ratio = max_px / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), _Img.LANCZOS)
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue()
    except Exception:
        return image_bytes  # fallback: return original if PIL not available


async def _upsert_global_product(_ignored_db: AsyncSession, p: ProductCache, force: bool = False):
    """Insert or update the shared GlobalProduct catalog entry.

    Uses its OWN isolated DB session so that any failure never affects the
    caller's transaction. Supports products with barcode OR article (no barcode).
    force=True: re-adds even if is_excluded (manual add/invoice). force=False: skips excluded (sync).
    """
    from backend.services.catalog_cleaner import (
        normalize_name, translate_category, detect_unit, _VALID_BARCODE_LENGTHS
    )
    from backend.database.connection import AsyncSessionLocal
    from sqlalchemy import text as _text
    import uuid as _uuid
    from loguru import logger

    barcode = (p.barcode or "").strip()
    article = (p.article or "").strip()

    if barcode and (not barcode.isdigit() or len(barcode) not in _VALID_BARCODE_LENGTHS):
        barcode = ""

    if not barcode and not article:
        return

    bc_key = barcode if barcode else f"article:{article}"
    clean_name = normalize_name(p.name or "")
    if not clean_name:
        return
    clean_cat = translate_category(p.category) if p.category else None
    clean_unit = p.unit or detect_unit(clean_name) or "шт"

    sess = _ignored_db
    use_own = sess is None
    if use_own:
        from backend.database.connection import AsyncSessionLocal
        _own = AsyncSessionLocal()
        sess = await _own.__aenter__()
    try:
        existing = await sess.execute(
            _text("SELECT is_excluded FROM global_products WHERE barcode = :bc"),
            {"bc": bc_key}
        )
        row = existing.fetchone()
        if row and row[0] and not force:
            return
        await sess.execute(_text("""
            INSERT INTO global_products
                (id, barcode, name, price, purchase_price, article, category, unit, description)
            VALUES
                (:id, :bc, :name, :price, :pp, :article, :category, :unit, :desc)
            ON CONFLICT (barcode) DO UPDATE SET
                name             = EXCLUDED.name,
                price            = COALESCE(EXCLUDED.price,          global_products.price),
                purchase_price   = COALESCE(EXCLUDED.purchase_price, global_products.purchase_price),
                article          = COALESCE(EXCLUDED.article,        global_products.article),
                category         = COALESCE(EXCLUDED.category,       global_products.category),
                unit             = COALESCE(EXCLUDED.unit,           global_products.unit),
                is_excluded      = FALSE
        """), {
            "id": _uuid.uuid4(), "bc": bc_key, "name": clean_name,
            "price": p.price, "pp": p.purchase_price,
            "article": article or p.article, "category": clean_cat,
            "unit": clean_unit, "desc": p.description,
        })
        if use_own:
            await sess.commit()
    except Exception as exc:
        logger.warning(f"_upsert_global_product failed for key={bc_key}: {exc}")
    finally:
        if use_own:
            await _own.__aexit__(None, None, None)


async def _upsert_global_product_from_dict(
    barcode: Optional[str], article: Optional[str], name: Optional[str],
    price=None, purchase_price=None, unit=None, category=None, description=None,
):
    """Background-task-safe global catalog upsert using its own isolated session."""
    from backend.services.catalog_cleaner import (
        normalize_name, translate_category, detect_unit, _VALID_BARCODE_LENGTHS
    )
    from backend.database.connection import AsyncSessionLocal
    from sqlalchemy import text as _text
    import uuid as _uuid
    bc = (barcode or "").strip()
    art = (article or "").strip()
    if bc and (not bc.isdigit() or len(bc) not in _VALID_BARCODE_LENGTHS):
        bc = ""
    if not bc and not art:
        return
    bc_key = bc if bc else f"article:{art}"
    clean_name = normalize_name(name or "")
    if not clean_name:
        return
    clean_cat = translate_category(category) if category else None
    clean_unit = unit or detect_unit(clean_name) or "шт"
    try:
        async with AsyncSessionLocal() as sess:
            row = (await sess.execute(
                _text("SELECT is_excluded FROM global_products WHERE barcode = :bc"),
                {"bc": bc_key}
            )).fetchone()
            if row and row[0]:
                return
            await sess.execute(_text("""
                INSERT INTO global_products
                    (id, barcode, name, price, purchase_price, article, category, unit)
                VALUES (:id, :bc, :name, :price, :pp, :article, :cat, :unit)
                ON CONFLICT (barcode) DO UPDATE SET
                    name           = EXCLUDED.name,
                    price          = COALESCE(EXCLUDED.price,         global_products.price),
                    purchase_price = COALESCE(EXCLUDED.purchase_price,global_products.purchase_price),
                    article        = COALESCE(EXCLUDED.article,       global_products.article),
                    category       = COALESCE(EXCLUDED.category,      global_products.category),
                    unit           = COALESCE(EXCLUDED.unit,          global_products.unit)
                WHERE global_products.is_excluded IS NOT TRUE
            """), {
                "id": _uuid.uuid4(), "bc": bc_key, "name": clean_name,
                "price": price, "pp": purchase_price,
                "article": art or article, "cat": clean_cat, "unit": clean_unit,
            })
            await sess.commit()
    except Exception as exc:
        logger.warning(f"_upsert_global_product_from_dict failed key={bc_key}: {exc}")


def _serialize_product(p: ProductCache) -> dict:
    return {
        "id": str(p.id),
        "store_id": str(p.store_id),
        "onec_id": p.onec_id,
        "name": p.name,
        "barcode": p.barcode,
        "article": p.article,
        "category": p.category,
        "price": p.price,
        "purchase_price": p.purchase_price,
        "quantity": p.quantity,
        "unit": p.unit,
        "description": p.description,
        "image_url": p.image_url,
        "is_active": p.is_active,
        "synced_at": p.synced_at,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


async def _check_store_access(store_id: UUID, user: User, db: AsyncSession) -> Store:
    result = await db.execute(
        select(Store).where(Store.id == store_id, Store.owner_id == user.id)
    )
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Магазин не найден")
    return store


async def _mark_deleted_in_onec(
    onec_url: str, onec_username: str, onec_password_enc: str,
    onec_id: str, name: str, article: str = "",
):
    """Mark product as deleted in 1C.

    Marks by onec_id AND by article (to catch original/duplicate pairs).
    """
    from backend.integrations.onec_integration import OneCClient
    from backend.core.security import decrypt_password
    from loguru import logger
    import urllib.parse
    try:
        client = OneCClient(onec_url, onec_username, decrypt_password(onec_password_enc))

        ids_to_mark = set()

        clean_id = str(onec_id).strip("{}")
        if clean_id:
            ids_to_mark.add(clean_id)

        if article and article.strip():
            art = article.strip()
            q = urllib.parse.quote(art.replace("'", "''"))
            ok2, data2 = await client._request_silent(
                "GET",
                f"odata/standard.odata/Catalog_Номенклатура?$format=json"
                f"&$filter=Артикул eq '{q}'&$select=Ref_Key&$top=20"
            )
            if ok2 and isinstance(data2, dict):
                for item in data2.get("value", []):
                    ref = str(item.get("Ref_Key", "")).strip("{}")
                    if ref:
                        ids_to_mark.add(ref)

        for ref_id in ids_to_mark:
            ok, resp = await client._request(
                "DELETE",
                f"odata/standard.odata/Catalog_Номенклатура(guid'{ref_id}')",
            )
            if ok:
                logger.info(f"[1C DEL] '{name}' id={ref_id} physically deleted")
            else:
                ok2, resp2 = await client._request(
                    "PATCH",
                    f"odata/standard.odata/Catalog_Номенклатура(guid'{ref_id}')?$format=json",
                    extra_headers={"Content-Type": "application/json"},
                    json={"DeletionMark": True},
                )
                logger.info(f"[1C DEL] '{name}' id={ref_id} marked ok={ok2} resp={str(resp2)[:60]}")
    except Exception as e:
        from loguru import logger as _log
        _log.error(f"[1C DEL] EXCEPTION for '{name}': {e}", exc_info=True)


async def _push_barcode_and_prices(
    onec_url: str, onec_username: str, onec_password_enc: str,
    onec_id: str, barcode: Optional[str], price: Optional[float],
    purchase_price: Optional[float], name: str, article: Optional[str],
    quantity: Optional[float] = None,
    use_accounting: bool = True,
    delay: int = 5,
):
    """Push barcode + prices + stock quantity to 1C after a delay so the entity is fully settled."""
    import asyncio
    from backend.integrations.onec_integration import OneCClient
    from backend.core.security import decrypt_password
    from loguru import logger

    logger.info(f"[1C P2] sleeping {delay}s before barcode push for '{name}' (onec_id={onec_id}, barcode={barcode})")
    await asyncio.sleep(delay)
    logger.info(f"[1C P2] woke up, pushing barcode for '{name}'")
    try:
        client = OneCClient(onec_url, onec_username, decrypt_password(onec_password_enc))
        clean_id = str(onec_id).strip("{}")

        class _S:
            pass
        snap = _S()
        snap.name = name
        snap.barcode = barcode
        snap.article = article
        snap.category = None

        upd_ok, upd_data = await client.update_product(clean_id, snap)
        logger.info(f"[1C P2] update_product ok={upd_ok}")
        if barcode and str(barcode).strip():
            bc_ok = await client.create_barcode(clean_id, str(barcode).strip())
            logger.info(f"[1C P2] create_barcode ok={bc_ok} barcode={barcode}")
        if price and price > 0:
            await client.set_price(clean_id, float(price), price_type_name="розн")
        if purchase_price and purchase_price > 0:
            await client.set_price(clean_id, float(purchase_price), price_type_name="закуп")
        if quantity and quantity > 0:
            st_ok = await client.set_stock(clean_id, float(quantity), float(price or 0),
                                           use_accounting=use_accounting)
            logger.info(f"[1C P2] set_stock ok={st_ok} qty={quantity} use_accounting={use_accounting}")
        logger.info(f"[1C P2] DONE for '{name}' barcode={barcode} qty={quantity} onec_id={clean_id}")
    except Exception as e:
        from loguru import logger as _log
        _log.error(f"[1C P2] EXCEPTION for '{name}': {e}", exc_info=True)


class _ProductSnapshot:
    """Lightweight product data carrier for background 1C push (no DB re-fetch needed)."""
    def __init__(self, id, name, barcode, price, purchase_price, onec_id, article, category, unit, description, quantity=None):
        self.id = id
        self.name = name
        self.barcode = barcode
        self.price = price
        self.purchase_price = purchase_price
        self.onec_id = onec_id
        self.article = article
        self.category = category
        self.unit = unit
        self.description = description
        self.quantity = quantity


async def _push_to_onec_bg(
    store_id: UUID,
    product_id: UUID,
    name: str,
    barcode: Optional[str],
    price: Optional[float],
    purchase_price: Optional[float],
    onec_id: Optional[str],
    article: Optional[str],
    category: Optional[str],
    unit: Optional[str],
    description: Optional[str],
    quantity: Optional[float] = None,
):
    """Push a product to 1C in the background. Data passed directly — no DB re-fetch."""
    from backend.integrations.onec_integration import OneCClient
    from backend.core.security import decrypt_password
    from backend.database.connection import AsyncSessionLocal
    from loguru import logger

    snap = _ProductSnapshot(
        id=product_id, name=name, barcode=barcode, price=price,
        purchase_price=purchase_price, onec_id=onec_id, article=article,
        category=category, unit=unit, description=description, quantity=quantity,
    )

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Integration).where(
                    Integration.store_id == store_id,
                    Integration.status == IntegrationStatus.active,
                )
            )
            integration = result.scalars().first()
            if not integration:
                return

            client = OneCClient(
                url=integration.onec_url,
                username=integration.onec_username,
                password=decrypt_password(integration.onec_password_encrypted),
            )

            if snap.onec_id:
                success, data = await client.update_product(snap.onec_id, snap)
                if not success:
                    logger.warning(f"[1C bg] update_product failed for '{snap.name}': {data}")
            else:
                success, data = await client.create_product(snap)
                if success and data and data.get("Ref_Key"):
                    snap.onec_id = str(data["Ref_Key"]).strip("{}")
                elif success and not snap.onec_id:
                    found_id = await client.find_product_by_name(snap.name)
                    if found_id:
                        snap.onec_id = found_id
                # For a newly created product, PATCH it immediately (sets Штрихкод + settles entity)
                if success and snap.onec_id:
                    await client.update_product(snap.onec_id, snap)

            # Push barcode / prices / stock independently — even if update_product failed
            # (product already exists in 1C with known onec_id, only stock/prices need updating)
            if snap.onec_id:
                clean_id = snap.onec_id.strip("{}")
                use_accounting = bool(integration.settings.get("use_accounting", False)) if integration.settings else False
                if snap.barcode and snap.barcode.strip():
                    await client.create_barcode(clean_id, snap.barcode.strip())
                if snap.price is not None and snap.price > 0:
                    await client.set_price(clean_id, float(snap.price), price_type_name="розн")
                if snap.purchase_price is not None and snap.purchase_price > 0:
                    await client.set_price(clean_id, float(snap.purchase_price), price_type_name="закуп")
                if snap.quantity is not None and snap.quantity >= 0:
                    st_ok = await client.set_stock(
                        clean_id, float(snap.quantity), float(snap.price or 0),
                        use_accounting=use_accounting,
                        replace=bool(snap.onec_id),  # replace when updating existing product
                    )
                    logger.info(f"[1C bg] set_stock ok={st_ok} qty={snap.quantity} replace={bool(snap.onec_id)}")
                # Save onec_id + synced_at back to DB
                await db.execute(
                    sa_update(ProductCache)
                    .where(ProductCache.id == product_id)
                    .values(onec_id=snap.onec_id, synced_at=datetime.now(timezone.utc))
                )
                await db.commit()
                logger.info(f"[1C bg] '{snap.name}' synced (onec_id={clean_id}, barcode={snap.barcode})")
            else:
                logger.warning(f"[1C bg] no onec_id resolved for '{snap.name}' — skipped")
        except Exception as e:
            logger.error(f"[1C bg] error for '{name}': {e}")


@router.get("/check-barcode")
async def check_barcode_global(
    barcode: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check barcode: own stores first (raw SQL), then any other store (cross-tenant)."""
    from sqlalchemy import text as _text
    from backend.database.connection import _is_sqlite
    # asyncpg (PostgreSQL) requires uuid.UUID objects for UUID columns; SQLite needs hex string
    uid = str(current_user.id).replace('-', '') if _is_sqlite else current_user.id
    bc = barcode.strip()

    # 1. Own stores — raw SQL, no ORM
    own = (await db.execute(_text(
        "SELECT pc.id, pc.store_id, pc.onec_id, pc.barcode, pc.name, pc.price, "
        "pc.purchase_price, pc.quantity, pc.unit, pc.article, pc.category, "
        "pc.description, pc.is_active, s.name AS store_name "
        "FROM products_cache pc "
        "JOIN stores s ON pc.store_id = s.id "
        "WHERE s.owner_id = :uid AND pc.barcode = :bc AND pc.is_active = :active "
        "LIMIT 1"
    ), {"uid": uid, "bc": bc, "active": True})).fetchone()

    if own:
        return {
            "found": True,
            "source": "own",
            "store_name": own[13],
            "product": {
                "id": own[0], "store_id": own[1], "onec_id": own[2],
                "barcode": own[3], "name": own[4], "price": own[5],
                "purchase_price": own[6], "quantity": own[7], "unit": own[8],
                "article": own[9], "category": own[10], "description": own[11],
                "is_active": bool(own[12]),
            },
        }

    # 2. Any other user's store — raw SQL cross-tenant search
    other = (await db.execute(_text(
        "SELECT pc.barcode, pc.name, pc.price, pc.purchase_price, "
        "pc.article, pc.category, pc.unit, pc.description "
        "FROM products_cache pc "
        "JOIN stores s ON pc.store_id = s.id "
        "WHERE s.owner_id != :uid AND pc.barcode = :bc AND pc.is_active = :active "
        "LIMIT 1"
    ), {"uid": uid, "bc": bc, "active": True})).fetchone()

    if other:
        return {
            "found": True,
            "source": "global",
            "store_name": "Общий каталог",
            "product": {
                "id": None, "store_id": None,
                "barcode": other[0], "name": other[1], "price": other[2],
                "purchase_price": other[3], "article": other[4],
                "category": other[5], "unit": other[6], "description": other[7],
                "quantity": 0, "is_active": True,
            },
        }

    # 3. GlobalProduct catalog (Open Food Facts imports)
    gp = (await db.execute(_text(
        "SELECT barcode, name, price, purchase_price, article, category, unit, description "
        "FROM global_products WHERE barcode = :bc AND is_excluded IS NOT TRUE LIMIT 1"
    ), {"bc": bc})).fetchone()

    if gp:
        return {
            "found": True,
            "source": "catalog",
            "store_name": "База товаров",
            "product": {
                "id": None, "store_id": None,
                "barcode": gp[0], "name": gp[1], "price": gp[2],
                "purchase_price": gp[3], "article": gp[4],
                "category": gp[5], "unit": gp[6], "description": gp[7],
                "quantity": 0, "is_active": True,
            },
        }

    return {"found": False, "product": None, "store_name": None}


@router.get("/search-global")
async def search_global_catalog(
    q: str = "",
    limit: int = 8,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search own products (all stores) first, then GlobalProduct catalog, then cross-tenant."""
    from sqlalchemy import text as _text
    from backend.database.connection import _is_sqlite
    uid = str(current_user.id).replace('-', '') if _is_sqlite else current_user.id
    q = q.strip()
    if len(q) < 2:
        return []

    results: list[dict] = []
    seen_names: set[str] = set()

    # 1. User's own products across ALL their stores (highest priority)
    own_rows = (await db.execute(_text(
        "SELECT pc.id, pc.store_id, pc.barcode, pc.name, pc.price, pc.purchase_price, "
        "pc.article, pc.category, pc.unit, pc.description, pc.quantity "
        "FROM products_cache pc "
        "JOIN stores s ON pc.store_id = s.id "
        "WHERE s.owner_id = :uid AND lower(pc.name) LIKE lower(:q) AND pc.is_active = :active "
        "ORDER BY pc.name LIMIT :lim"
    ), {"uid": uid, "q": f"%{q}%", "active": True, "lim": limit})).fetchall()

    for r in own_rows:
        nl = r[3].lower()
        if nl not in seen_names:
            results.append({
                "id": str(r[0]), "store_id": str(r[1]), "barcode": r[2], "name": r[3],
                "price": r[4], "purchase_price": r[5], "article": r[6],
                "category": r[7], "unit": r[8], "description": r[9],
                "quantity": r[10] or 0, "source": "own_store",
            })
            seen_names.add(nl)
        if len(results) >= limit:
            return results

    # 2. GlobalProduct catalog (Open Food Facts / imported)
    remaining = limit - len(results)
    if remaining > 0:
        gp_rows = (await db.execute(_text(
            "SELECT barcode, name, price, purchase_price, article, category, unit, description "
            "FROM global_products "
            "WHERE lower(name) LIKE lower(:q) AND is_excluded IS NOT TRUE "
            "ORDER BY name LIMIT :lim"
        ), {"q": f"%{q}%", "lim": remaining})).fetchall()
        for r in gp_rows:
            nl = r[1].lower()
            if nl not in seen_names:
                results.append({
                    "id": None, "store_id": None, "barcode": r[0], "name": r[1],
                    "price": r[2], "purchase_price": r[3], "article": r[4],
                    "category": r[5], "unit": r[6], "description": r[7],
                    "quantity": 0, "source": "catalog",
                })
                seen_names.add(nl)

    # 3. Cross-tenant products_cache (other users)
    remaining = limit - len(results)
    if remaining > 0:
        pc_rows = (await db.execute(_text(
            "SELECT DISTINCT pc.barcode, pc.name, pc.price, pc.purchase_price, "
            "pc.article, pc.category, pc.unit, pc.description "
            "FROM products_cache pc "
            "WHERE lower(pc.name) LIKE lower(:q) AND pc.is_active = :active "
            "LIMIT :lim"
        ), {"q": f"%{q}%", "lim": remaining * 2, "active": True})).fetchall()
        for r in pc_rows:
            nl = r[1].lower()
            if nl not in seen_names:
                results.append({
                    "id": None, "store_id": None, "barcode": r[0], "name": r[1],
                    "price": r[2], "purchase_price": r[3], "article": r[4],
                    "category": r[5], "unit": r[6], "description": r[7],
                    "quantity": 0, "source": "user_catalog",
                })
                seen_names.add(nl)
            if len(results) >= limit:
                break

    return results


@router.get("/{store_id}")
async def list_products(
    store_id: UUID,
    background_tasks: BackgroundTasks,
    search: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_store_access(store_id, current_user, db)

    # On first page open (no search/filter) — kick off 1C sync if stale > 2 min
    if page == 1 and not search and not category:
        from backend.database.models import Integration, IntegrationStatus
        from datetime import timezone as _tz
        integ_row = (await db.execute(
            select(Integration).where(
                Integration.store_id == store_id,
                Integration.status == IntegrationStatus.active,
            )
        )).scalars().first()
        if integ_row:
            stale = True
            if integ_row.last_sync_at:
                age = (datetime.now(_tz.utc) - integ_row.last_sync_at).total_seconds()
                stale = age > 120  # re-sync if older than 2 minutes
            if stale:
                from backend.api.stores import _run_sync_in_background
                background_tasks.add_task(
                    _run_sync_in_background, store_id, integ_row.id
                )

    query = select(ProductCache).where(
        and_(ProductCache.store_id == store_id, ProductCache.is_active == True)
    )
    if search:
        query = query.where(
            ProductCache.name.ilike(f"%{search}%") |
            ProductCache.barcode.ilike(f"%{search}%") |
            ProductCache.article.ilike(f"%{search}%")
        )
    if category:
        query = query.where(ProductCache.category == category)

    query = query.offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    products = result.scalars().all()
    return [_serialize_product(p) for p in products]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    store_id = UUID(payload.store_id)
    await _check_store_access(store_id, current_user, db)

    product = ProductCache(
        store_id=store_id,
        name=payload.name,
        price=payload.price,
        purchase_price=payload.purchase_price,
        barcode=payload.barcode,
        article=payload.article,
        category=payload.category,
        quantity=payload.quantity or 0,
        unit=payload.unit or "шт",
        description=payload.description,
    )
    db.add(product)
    await db.flush()

    await _upsert_global_product(db, product, force=True)

    log = Log(
        user_id=current_user.id,
        store_id=store_id,
        level=LogLevel.info,
        action="product_created",
        message=f"Создан товар: {payload.name}",
        meta={"product_id": str(product.id)},
    )
    db.add(log)
    await db.commit()
    result = _serialize_product(product)

    # ── Phase 1: create product in 1C synchronously, save onec_id ──
    try:
        integ_r = await db.execute(
            select(Integration).where(
                Integration.store_id == store_id,
            ).order_by(
                Integration.status  # "active" < "error" < "inactive" alphabetically → active first
            )
        )
        integration = integ_r.scalars().first()
        if integration:
            from backend.integrations.onec_integration import OneCClient
            from backend.core.security import decrypt_password
            from loguru import logger as _log
            import asyncio as _aio
            client = OneCClient(
                url=integration.onec_url,
                username=integration.onec_username,
                password=decrypt_password(integration.onec_password_encrypted),
            )
            _log.info(f"[1C P1] creating product '{product.name}' barcode={product.barcode}")
            ok, data = await client.create_product(product)
            _log.info(f"[1C P1] create_product ok={ok} data_keys={list(data.keys()) if isinstance(data, dict) else data}")
            if ok and data and data.get("Ref_Key"):
                product.onec_id = str(data["Ref_Key"]).strip("{}")
                await db.commit()
                _log.info(f"[1C P1] onec_id saved: {product.onec_id}")
            elif ok and not product.onec_id:
                _log.warning(f"[1C P1] no Ref_Key in response, trying find_by_name")
                found = await client.find_product_by_name(product.name)
                _log.info(f"[1C P1] find_by_name result: {found}")
                if found:
                    product.onec_id = found
                    await db.commit()
            else:
                _log.error(f"[1C P1] create_product FAILED: ok={ok} data={data}")

            # ── Phase 2: barcode + prices after 5s delay (entity must settle in 1C first) ──
            if product.onec_id:
                _settings = integration.settings or {}
                _aio.ensure_future(_push_barcode_and_prices(
                    onec_url=integration.onec_url,
                    onec_username=integration.onec_username,
                    onec_password_enc=integration.onec_password_encrypted,
                    onec_id=product.onec_id,
                    barcode=product.barcode,
                    price=product.price,
                    purchase_price=product.purchase_price,
                    name=product.name,
                    article=product.article,
                    quantity=product.quantity,
                    use_accounting=bool(_settings.get("use_accounting", False)),
                    delay=5,
                ))
                _log.info(f"[1C P2] '{product.name}' barcode push scheduled in 5s (onec_id={product.onec_id})")
            else:
                _log.error(f"[1C P1] no onec_id — barcode push skipped for '{product.name}'")
    except Exception as _e:
        from loguru import logger as _log
        _log.error(f"[1C create] EXCEPTION for '{product.name}': {_e}", exc_info=True)

    return result


@router.post("/scan-barcode")
async def scan_barcode(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    from backend.services.barcode_service import BarcodeService

    contents = await file.read()
    service = BarcodeService()
    barcodes = service.decode(contents)
    if not barcodes:
        raise HTTPException(status_code=422, detail="Штрих-код не распознан")
    return {"barcodes": barcodes}


@router.post("/recognize-photo")
async def recognize_photo(
    store_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.ai_service import AIService
    from backend.services.barcode_service import BarcodeService
    import asyncio

    store_id_uuid = UUID(store_id)
    await _check_store_access(store_id_uuid, current_user, db)

    contents = await file.read()

    # Step 1: try barcode detection locally (fast, <1s, no AI needed)
    loop = asyncio.get_event_loop()
    barcodes = await loop.run_in_executor(None, BarcodeService().decode, contents)
    if barcodes:
        return {"recognized": {"barcode": barcodes[0]}, "ocr_text": "", "source": "barcode"}

    # Step 2: no barcode → compress + AI vision
    compressed = await loop.run_in_executor(None, _compress_image, contents, 512)
    ai_service = AIService()
    product_data = await ai_service.recognize_product_from_image("", compressed)
    return {"recognized": product_data, "ocr_text": "", "source": "ai"}


class InvoiceProductSave(BaseModel):
    name: str
    article: Optional[str] = None
    barcode: Optional[str] = None
    quantity: Optional[float] = 1.0
    unit: Optional[str] = "шт"
    purchase_price: Optional[float] = None
    price: Optional[float] = None
    category: Optional[str] = None
    description: Optional[str] = None
    existing_id: Optional[str] = None  # if set, update existing product


@router.post("/upload-invoice")
async def upload_invoice(
    store_id: str = Form(...),
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.ai_service import AIService
    from backend.services.ocr_service import OCRService
    from sqlalchemy import func as _func

    store_id_uuid = UUID(store_id)
    await _check_store_access(store_id_uuid, current_user, db)

    all_image_bytes: List[bytes] = []
    combined_text_parts: List[str] = []
    all_pdf = True

    for f in files:
        contents = await f.read()
        content_type = f.content_type or "image/jpeg"
        all_image_bytes.append(contents)
        if "pdf" in content_type:
            ocr_service = OCRService()
            extracted = ocr_service.extract_from_file(contents, content_type)
            if extracted.strip():
                combined_text_parts.append(extracted)
        else:
            all_pdf = False

    ai_service = AIService()
    try:
        if combined_text_parts and all_pdf:
            products = await ai_service.parse_invoice("\n\n".join(combined_text_parts))
        else:
            products = await ai_service.parse_invoice_from_images(all_image_bytes)
    except Exception as exc:
        err_str = str(exc)
        if "402" in err_str or "credits" in err_str.lower() or "afford" in err_str.lower():
            raise HTTPException(
                status_code=402,
                detail="Недостаточно кредитов AI. Пополните баланс на openrouter.ai и попробуйте снова.",
            )
        logger.error(f"Invoice AI error: {exc}")
        raise HTTPException(status_code=503, detail="Ошибка сервиса AI. Попробуйте позже.")

    # DB matching — enrich each product from store products and global catalog
    for p in products:
        p.setdefault("_matched", False)
        p.setdefault("_existing_id", None)
        p.setdefault("_global_match", False)
        barcode = p.get("barcode")
        name = (p.get("name") or "").strip()

        # 1. Match by barcode in store products
        if barcode:
            r = await db.execute(
                select(ProductCache).where(
                    ProductCache.store_id == store_id_uuid,
                    ProductCache.barcode == barcode,
                    ProductCache.is_active == True,
                )
            )
            existing = r.scalar_one_or_none()
            if existing:
                p["_matched"] = True
                p["_existing_id"] = str(existing.id)
                if not p.get("price") and existing.price:
                    p["price"] = float(existing.price)
                if not p.get("category") and existing.category:
                    p["category"] = existing.category
                if not p.get("article") and existing.article:
                    p["article"] = existing.article
                continue

        # 2. Match by barcode in global catalog
        if barcode:
            r = await db.execute(
                select(GlobalProduct).where(GlobalProduct.barcode == barcode)
            )
            gp = r.scalar_one_or_none()
            if gp:
                p["_global_match"] = True
                if not p.get("name") or len(p.get("name", "")) < 3:
                    p["name"] = gp.name
                if not p.get("article") and gp.article:
                    p["article"] = gp.article
                if not p.get("category") and gp.category:
                    p["category"] = gp.category
                continue

        # 3. Match by article in store products
        article = (p.get("article") or "").strip()
        if article and not p.get("_matched"):
            r = await db.execute(
                select(ProductCache).where(
                    ProductCache.store_id == store_id_uuid,
                    ProductCache.article == article,
                    ProductCache.is_active == True,
                )
            )
            existing = r.scalar_one_or_none()
            if existing:
                p["_matched"] = True
                p["_existing_id"] = str(existing.id)
                if not p.get("barcode") and existing.barcode:
                    p["barcode"] = existing.barcode
                if not p.get("price") and existing.price:
                    p["price"] = float(existing.price)
                if not p.get("category") and existing.category:
                    p["category"] = existing.category
                continue

        # 4. Match by exact name (case-insensitive) in store products
        if name and not p.get("_matched"):
            r = await db.execute(
                select(ProductCache).where(
                    ProductCache.store_id == store_id_uuid,
                    _func.lower(ProductCache.name) == name.lower(),
                    ProductCache.is_active == True,
                )
            )
            existing = r.scalar_one_or_none()
            if existing:
                p["_matched"] = True
                p["_existing_id"] = str(existing.id)
                if not p.get("barcode") and existing.barcode:
                    p["barcode"] = existing.barcode
                if not p.get("price") and existing.price:
                    p["price"] = float(existing.price)
                if not p.get("category") and existing.category:
                    p["category"] = existing.category

    log = Log(
        user_id=current_user.id,
        store_id=store_id_uuid,
        level=LogLevel.info,
        action="invoice_uploaded",
        message=f"Накладная распознана: {len(files)} фото",
        meta={"photos": len(files), "products_found": len(products)},
    )
    db.add(log)
    await db.commit()

    return {"products": products, "count": len(products)}


@router.post("/save-invoice")
async def save_invoice_products(
    store_id: str,
    products: List[InvoiceProductSave],
    background_tasks: BackgroundTasks,
    sync_to_onec: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func as _func
    store_id_uuid = UUID(store_id)
    await _check_store_access(store_id_uuid, current_user, db)

    saved = []
    for p in products:
        if not p.name or not p.name.strip():
            continue
        product = None

        # 1) Look up by explicit id
        if p.existing_id:
            try:
                r = await db.execute(
                    select(ProductCache).where(
                        ProductCache.id == UUID(p.existing_id),
                        ProductCache.store_id == store_id_uuid,
                        ProductCache.is_active == True,
                    ).limit(1)
                )
                product = r.scalar_one_or_none()
            except Exception:
                product = None

        # 2) Dedup by article
        if not product and p.article and p.article.strip():
            r = await db.execute(
                select(ProductCache).where(
                    ProductCache.store_id == store_id_uuid,
                    ProductCache.article == p.article.strip(),
                    ProductCache.is_active == True,
                ).limit(1)
            )
            product = r.scalar_one_or_none()

        # 3) Dedup by name (case-insensitive)
        if not product and p.name and p.name.strip():
            r = await db.execute(
                select(ProductCache).where(
                    ProductCache.store_id == store_id_uuid,
                    _func.lower(ProductCache.name) == p.name.strip().lower(),
                    ProductCache.is_active == True,
                ).limit(1)
            )
            product = r.scalar_one_or_none()

        if product:
            if p.quantity is not None:
                product.quantity = (product.quantity or 0) + p.quantity
            if p.purchase_price is not None:
                product.purchase_price = p.purchase_price
            if p.price is not None and p.price > 0:
                product.price = p.price
            if p.barcode and not product.barcode:
                product.barcode = p.barcode
            if p.article and not product.article:
                product.article = p.article
            if p.category and not product.category:
                product.category = p.category
        else:
            product = ProductCache(
                store_id=store_id_uuid,
                name=p.name.strip(),
                price=p.price,
                purchase_price=p.purchase_price,
                barcode=p.barcode,
                article=p.article,
                category=p.category,
                quantity=p.quantity or 0,
                unit=p.unit or "шт",
                description=p.description,
            )
            db.add(product)
            await db.flush()
        saved.append(product)

    # Serialize BEFORE commit to avoid expired-object issues
    serialized = [_serialize_product(p) for p in saved]

    # Collect 1C push data BEFORE commit (while ORM objects are fresh)
    onec_push_list = []
    if sync_to_onec and saved:
        r2 = await db.execute(
            select(Integration).where(
                Integration.store_id == store_id_uuid,
                Integration.status == IntegrationStatus.active,
            ).limit(1)
        )
        integration = r2.scalar_one_or_none()
        if integration:
            from backend.integrations.onec_integration import OneCClient
            from backend.core.security import decrypt_password
            client = OneCClient(
                url=integration.onec_url,
                username=integration.onec_username,
                password=decrypt_password(integration.onec_password_encrypted),
            )
            _settings = integration.settings or {}
            use_accounting = bool(_settings.get("use_accounting", False))
            for product in saved:
                try:
                    onec_id = product.onec_id
                    if not onec_id:
                        success, data = await client.create_product(product)
                        if success and data and data.get("Ref_Key"):
                            onec_id = str(data["Ref_Key"]).strip("{}")
                            product.onec_id = onec_id
                    if onec_id:
                        onec_push_list.append(dict(
                            onec_url=integration.onec_url,
                            onec_username=integration.onec_username,
                            onec_password_enc=integration.onec_password_encrypted,
                            onec_id=onec_id,
                            barcode=product.barcode,
                            price=float(product.price) if product.price else None,
                            purchase_price=float(product.purchase_price) if product.purchase_price else None,
                            name=product.name,
                            article=product.article,
                            quantity=float(product.quantity) if product.quantity else None,
                            use_accounting=use_accounting,
                        ))
                except Exception as e:
                    logger.warning(f"1C sync failed for {product.name}: {e}")

    # Single commit
    await db.commit()

    # Schedule 1C pushes as background tasks (after commit, no ORM objects needed)
    for kwargs in onec_push_list:
        background_tasks.add_task(_push_barcode_and_prices, **kwargs, delay=5)

    # Upsert global catalog in background (no DB session issues)
    for s in serialized:
        if s.get("barcode") or s.get("article"):
            background_tasks.add_task(
                _upsert_global_product_from_dict,
                s.get("barcode"), s.get("article"), s.get("name"),
                s.get("price"), s.get("purchase_price"),
                s.get("unit"), s.get("category"), s.get("description"),
            )

    return {"saved": len(saved), "products": serialized}


@router.post("/bulk-create")
async def bulk_create_products(
    store_id: str,
    products: List[ProductCreate],
    sync_to_onec: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    store_id_uuid = UUID(store_id)
    await _check_store_access(store_id_uuid, current_user, db)

    created = []
    for p in products:
        product = ProductCache(
            store_id=store_id_uuid,
            name=p.name,
            price=p.price,
            purchase_price=p.purchase_price,
            barcode=p.barcode,
            article=p.article,
            category=p.category,
            quantity=p.quantity or 0,
            unit=p.unit or "шт",
            description=p.description,
        )
        db.add(product)
        created.append(product)

    await db.flush()

    if sync_to_onec:
        result = await db.execute(
            select(Integration).where(
                Integration.store_id == store_id_uuid,
                Integration.status == IntegrationStatus.active,
            )
        )
        integration = result.scalar_one_or_none()
        if integration:
            from backend.integrations.onec_integration import OneCClient
            from backend.core.security import decrypt_password

            client = OneCClient(
                url=integration.onec_url,
                username=integration.onec_username,
                password=decrypt_password(integration.onec_password_encrypted),
            )
            for product in created:
                await client.create_product(product)

    return {"created": len(created), "products": [_serialize_product(p) for p in created]}


@router.post("/quick-add")
async def quick_add_product(
    store_id: str = Form(...),
    text: str = Form(...),
    barcode: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI parses free-form text + optional barcode and creates the product directly."""
    from backend.services.ai_service import AIService

    await _check_store_access(UUID(store_id), current_user, db)
    ai_service = AIService()

    full_text = text
    if barcode:
        full_text = f"{text}\nШтрих-код: {barcode}"

    data = await ai_service.extract_product_from_text(full_text)
    if not data.get("name"):
        data["name"] = text[:100]
    if barcode:
        data["barcode"] = barcode

    product = ProductCache(
        id=uuid.uuid4(),
        store_id=UUID(store_id),
        name=data.get("name", text[:100]),
        barcode=data.get("barcode"),
        article=data.get("article"),
        category=data.get("category"),
        price=data.get("price"),
        purchase_price=data.get("purchase_price"),
        quantity=data.get("quantity", 0),
        unit=data.get("unit", "шт"),
        description=data.get("description"),
        is_active=True,
    )
    db.add(product)
    await db.flush()
    result = _serialize_product(product)
    await db.commit()
    await _upsert_global_product(db, product, force=True)
    # 1C push runs in background — does not block response
    import asyncio
    asyncio.ensure_future(_push_to_onec_bg(
        UUID(store_id), product.id,
        product.name, product.barcode, product.price, product.purchase_price,
        product.onec_id, product.article, product.category, product.unit, product.description
    ))
    return result


@router.post("/parse-text")
async def parse_product_from_text(
    text: str = Form(...),
    current_user: User = Depends(get_current_user),
):
    """Parse free-form text description into structured product data using AI."""
    from backend.services.ai_service import AIService

    ai_service = AIService()
    result = await ai_service.extract_product_from_text(text)
    return result


@router.get("/detail/{product_id}")
async def get_product(
    product_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ProductCache).where(ProductCache.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    await _check_store_access(product.store_id, current_user, db)
    return _serialize_product(product)


@router.put("/detail/{product_id}")
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ProductCache).where(ProductCache.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    await _check_store_access(product.store_id, current_user, db)

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(product, field, value)

    await _upsert_global_product(db, product, force=True)
    result = _serialize_product(product)
    await db.commit()
    quantity_changed = payload.model_dump(exclude_none=True).get("quantity") is not None
    background_tasks.add_task(
        _push_to_onec_bg, product.store_id, product.id,
        product.name, product.barcode, product.price, product.purchase_price,
        product.onec_id, product.article, product.category, product.unit, product.description,
        product.quantity if quantity_changed else None,
    )
    return result


@router.post("/detail/{product_id}/pull-from-1c")
async def pull_product_from_onec(
    product_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pull latest prices, barcode, stock for ONE product from 1C → update DB immediately."""
    from backend.integrations.onec_integration import OneCClient
    from backend.core.security import decrypt_password

    result_db = await db.execute(select(ProductCache).where(ProductCache.id == product_id))
    product = result_db.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    await _check_store_access(product.store_id, current_user, db)

    integ_result = await db.execute(
        select(Integration).where(
            Integration.store_id == product.store_id,
            Integration.status == IntegrationStatus.active,
        )
    )
    integration = integ_result.scalars().first()
    if not integration:
        raise HTTPException(status_code=400, detail="Нет активной интеграции с 1С")

    client = OneCClient(
        url=integration.onec_url,
        username=integration.onec_username,
        password=decrypt_password(integration.onec_password_encrypted),
    )

    onec_id = (product.onec_id or "").strip("{}")
    if not onec_id:
        raise HTTPException(status_code=400, detail="Товар не привязан к 1С (нет onec_id)")

    updated = {}

    # ── Prices ──
    retail_map, purchase_map = await client._classify_all_prices()
    if onec_id in retail_map and retail_map[onec_id]:
        product.price = retail_map[onec_id]
        updated["price"] = retail_map[onec_id]
    if onec_id in purchase_map and purchase_map[onec_id]:
        product.purchase_price = purchase_map[onec_id]
        updated["purchase_price"] = purchase_map[onec_id]

    # ── Barcode ──
    barcodes = await client.get_barcodes()
    bc = barcodes.get(onec_id) or barcodes.get("{" + onec_id + "}")
    if bc:
        product.barcode = bc
        updated["barcode"] = bc

    # ── Stock ──
    ok_q, balances = await client.get_stock_balances()
    if ok_q and balances:
        for bal in balances:
            if str(bal.get("onec_id", "")).strip("{}") == onec_id:
                product.quantity = float(bal.get("quantity", 0) or 0)
                updated["quantity"] = product.quantity
                break

    from datetime import datetime, timezone
    product.synced_at = datetime.now(timezone.utc)
    await db.commit()

    return {"updated": updated, "product": _serialize_product(product)}


@router.post("/detail/{product_id}/sync-to-onec")
async def sync_product_to_onec(
    product_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Synchronously push product → 1C and return full step-by-step result for debugging."""
    from backend.integrations.onec_integration import OneCClient
    from backend.core.security import decrypt_password

    result_db = await db.execute(select(ProductCache).where(ProductCache.id == product_id))
    product = result_db.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    await _check_store_access(product.store_id, current_user, db)

    integ_result = await db.execute(
        select(Integration).where(
            Integration.store_id == product.store_id,
            Integration.status == IntegrationStatus.active,
        )
    )
    integration = integ_result.scalars().first()
    if not integration:
        raise HTTPException(status_code=400, detail="Нет активной интеграции с 1С")

    client = OneCClient(
        url=integration.onec_url,
        username=integration.onec_username,
        password=decrypt_password(integration.onec_password_encrypted),
    )

    steps = {}

    # Step 1: create or update product
    if product.onec_id:
        ok, data = await client.update_product(product.onec_id, product)
        steps["product"] = {"action": "update", "ok": ok, "onec_id": product.onec_id,
                            "resp": str(data)[:300]}
    else:
        ok, data = await client.create_product(product)
        if ok and data and data.get("Ref_Key"):
            product.onec_id = str(data["Ref_Key"]).strip("{}")
            await db.commit()
        steps["product"] = {"action": "create", "ok": ok,
                            "onec_id": product.onec_id, "resp": str(data)[:300]}

    clean_id = (product.onec_id or "").strip("{}")
    if not clean_id:
        return {"product_name": product.name, "onec_id": None,
                "steps": steps, "probe": None}

    # Step 2: sync actual barcode + prices → 1C
    if product.barcode and product.barcode.strip():
        ok_bc = await client.create_barcode(clean_id, product.barcode.strip())
        steps["barcode"] = {"ok": ok_bc, "barcode": product.barcode}
    if product.price and product.price > 0:
        ok_rp = await client.set_price(clean_id, float(product.price), price_type_name="розн")
        steps["retail_price"] = {"ok": ok_rp, "price": product.price}
    if product.purchase_price and product.purchase_price > 0:
        ok_pp = await client.set_price(clean_id, float(product.purchase_price), price_type_name="закуп")
        steps["purchase_price"] = {"ok": ok_pp, "price": product.purchase_price}

    # Step 2b: pull back latest prices FROM 1C → update DB immediately
    retail_map, purchase_map = await client._classify_all_prices()
    updated_from_1c = {}
    if clean_id in retail_map and retail_map[clean_id]:
        product.price = retail_map[clean_id]
        updated_from_1c["price"] = retail_map[clean_id]
    if clean_id in purchase_map and purchase_map[clean_id]:
        product.purchase_price = purchase_map[clean_id]
        updated_from_1c["purchase_price"] = purchase_map[clean_id]
    if updated_from_1c:
        await db.commit()
        steps["pulled_from_1c"] = updated_from_1c

    # Step 3: diagnostic probe
    test_bc = (product.barcode or "").strip() or "4607141232117"
    test_price = float(product.price or 100.0)
    probe = await client.probe_barcode_price(clean_id, test_bc, test_price)

    return {
        "product_name": product.name,
        "onec_id": clean_id,
        "steps": steps,
        "probe": probe,
    }


class EnrichRequest(BaseModel):
    name: str
    barcode: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None


@router.post("/ai-enrich")
async def ai_enrich_product(
    payload: EnrichRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fast AI normalization of a single product. Persists result to global_products."""
    from backend.services.ai_service import AIService
    import json as _json
    from sqlalchemy import text as _text
    from loguru import logger as _log

    ai = AIService()
    prompt = (
        "Нормализуй товар для российского ритейла. "
        "Верни ТОЛЬКО JSON без пояснений, без markdown:\n"
        '{"name":"название на рус","category":"категория","unit":"шт"}\n\n'
        f'Название: {payload.name!r}\n'
        f'Категория: {payload.category or ""!r}\n'
        f'Единица: {payload.unit or ""!r}'
    )
    try:
        raw = await ai._call([{"role": "user", "content": prompt}], max_tokens=200, fast=True)
        import re as _re
        m = _re.search(r'\{[^}]+\}', raw, _re.DOTALL)
        enriched = _json.loads(m.group()) if m else {}
    except Exception as e:
        _log.warning(f"ai-enrich failed: {e}")
        enriched = {}

    name = (enriched.get("name") or payload.name).strip()[:255]
    category = (enriched.get("category") or payload.category or "").strip()[:100] or None
    unit = (enriched.get("unit") or payload.unit or "шт").strip()[:20]

    # Persist improved data back to global_products
    if payload.barcode:
        try:
            from sqlalchemy import text as _t
            await db.execute(_t(
                "UPDATE global_products SET name=:n, category=:c, unit=:u WHERE barcode=:b"
            ), {"n": name, "c": category, "u": unit, "b": payload.barcode.strip()})
            await db.commit()
        except Exception as exc:
            _log.warning(f"ai-enrich persist failed: {exc}")

    return {"name": name, "category": category, "unit": unit}


@router.get("/ai-status")
async def ai_status(current_user: User = Depends(get_current_user)):
    """Diagnostic endpoint: check which AI mode is active and test a quick call."""
    from backend.services.ai_service import AIService
    from backend.config import settings
    svc = AIService()
    test_ok = False
    test_result = None
    try:
        result = await svc.extract_product_from_text("тест молоко 1л")
        test_ok = bool(result.get("name"))
        test_result = result.get("name")
    except Exception as e:
        test_result = str(e)
    return {
        "mode": svc._mode,
        "model": svc._model,
        "openrouter_key_set": bool(settings.OPENROUTER_API_KEY),
        "anthropic_key_set": bool(settings.ANTHROPIC_API_KEY),
        "test_ok": test_ok,
        "test_name": test_result,
    }


@router.delete("/detail/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ProductCache).where(ProductCache.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    await _check_store_access(product.store_id, current_user, db)
    # Save before commit — async SQLAlchemy expires objects after commit
    _store_id = product.store_id
    _onec_id = product.onec_id
    _name = product.name
    product.is_active = False
    await db.commit()

    if _onec_id:
        integ_r = await db.execute(
            select(Integration).where(Integration.store_id == _store_id)
            .order_by(Integration.status)
        )
        integration = integ_r.scalars().first()
        if integration:
            import asyncio as _aio
            _aio.ensure_future(_mark_deleted_in_onec(
                onec_url=integration.onec_url,
                onec_username=integration.onec_username,
                onec_password_enc=integration.onec_password_encrypted,
                onec_id=_onec_id,
                name=_name,
            ))


def _detect_col(headers: list, candidates: list) -> Optional[str]:
    """Find first matching column name (case-insensitive)."""
    low = {h.lower().strip(): h for h in headers}
    for c in candidates:
        if c.lower() in low:
            return low[c.lower()]
    return None


def _parse_float(val: str) -> Optional[float]:
    if not val:
        return None
    try:
        return float(val.replace(',', '.').replace(' ', '').replace('\u00a0', ''))
    except Exception:
        return None


@router.post("/import-csv")
async def import_csv(
    store_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import products from CSV. Supports Open Food Facts and custom CSV formats."""
    import csv
    import io

    store_id_uuid = UUID(store_id)
    await _check_store_access(store_id_uuid, current_user, db)

    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1251", errors="replace")

    reader = csv.DictReader(io.StringIO(text), delimiter="\t" if "\t" in text[:500] else ",")
    headers = reader.fieldnames or []

    col_name = _detect_col(headers, [
        "product_name_ru", "product_name_fr", "product_name",
        "name", "название", "наименование", "товар", "Наименование",
    ])
    col_barcode = _detect_col(headers, ["code", "barcode", "ean", "штрих-код", "штрих_код", "Штрихкод"])
    col_category = _detect_col(headers, [
        "main_category_ru", "categories_ru", "category", "categories",
        "категория", "Категория", "группа",
    ])
    col_price = _detect_col(headers, ["price", "цена", "Цена", "стоимость"])
    col_purchase = _detect_col(headers, ["purchase_price", "закупка", "Закупка", "себестоимость"])
    col_unit = _detect_col(headers, ["unit", "единица", "Единица", "ед.изм", "quantity"])
    col_brand = _detect_col(headers, ["brands", "brand", "бренд", "производитель"])
    col_desc = _detect_col(headers, ["generic_name_ru", "generic_name", "description", "описание"])

    if not col_name:
        raise HTTPException(status_code=400, detail="Не найдена колонка с названием товара. Ожидается: name, product_name, название")

    created_count = 0
    skipped_count = 0
    batch = []
    BATCH_SIZE = 200

    async def flush_batch(b: list):
        nonlocal created_count
        db.add_all(b)
        await db.flush()
        created_count += len(b)

    from backend.services.catalog_cleaner import (
        normalize_name, translate_category, detect_unit, _VALID_BARCODE_LENGTHS
    )

    for row in reader:
        raw_name = row.get(col_name, "").strip() if col_name else ""
        brand = row.get(col_brand, "").strip() if col_brand else ""
        name = normalize_name(raw_name, vendor=brand)
        if not name:
            skipped_count += 1
            continue

        barcode = row.get(col_barcode, "").strip() if col_barcode else None
        if barcode:
            if not barcode.isdigit() or len(barcode) not in _VALID_BARCODE_LENGTHS:
                barcode = None

        category_raw = row.get(col_category, "").strip() if col_category else None
        category = translate_category(category_raw) if category_raw else None

        raw_unit = (row.get(col_unit, "").strip()[:20] if col_unit else None)
        unit = raw_unit or detect_unit(name) or "шт"

        product = ProductCache(
            id=uuid.uuid4(),
            store_id=store_id_uuid,
            name=name,
            barcode=barcode,
            category=category,
            price=_parse_float(row.get(col_price, "") if col_price else ""),
            purchase_price=_parse_float(row.get(col_purchase, "") if col_purchase else ""),
            unit=unit,
            description=(row.get(col_desc, "").strip()[:500] if col_desc else None) or None,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        batch.append(product)
        if len(batch) >= BATCH_SIZE:
            await flush_batch(batch)
            batch = []

    if batch:
        await flush_batch(batch)

    await db.commit()

    # Push imported products with barcodes to global catalog
    try:
        from sqlalchemy import text as _txt
        res = await db.execute(_txt(
            "SELECT id, barcode, name, price, purchase_price, article, category, unit, description "
            "FROM products_cache WHERE store_id=:sid AND is_active=true AND barcode IS NOT NULL"
        ), {"sid": str(store_id_uuid)})
        for r in res.fetchall():
            class _P:
                pass
            p = _P()
            p.barcode = r[1]; p.name = r[2]; p.price = r[3]
            p.purchase_price = r[4]; p.article = r[5]
            p.category = r[6]; p.unit = r[7]; p.description = r[8]
            await _upsert_global_product(db, p, force=True)
        await db.commit()
    except Exception as _e:
        _log.warning(f"CSV import global upsert failed: {_e}")
    return {
        "imported": created_count,
        "skipped": skipped_count,
        "columns_detected": {
            "name": col_name,
            "barcode": col_barcode,
            "category": col_category,
            "price": col_price,
            "unit": col_unit,
        },
    }


class BulkDeleteRequest(BaseModel):
    ids: List[UUID]


@router.delete("/bulk-delete")
async def bulk_delete_products(
    body: BulkDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete multiple products. Only products owned by the current user."""
    if not body.ids:
        return {"deleted": 0}

    logger.info(f"bulk_delete: received {len(body.ids)} ids from user={current_user.id}")
    result = await db.execute(
        select(ProductCache, Store)
        .join(Store, ProductCache.store_id == Store.id)
        .where(
            ProductCache.id.in_(body.ids),
            ProductCache.is_active == True,
            Store.owner_id == current_user.id,
        )
    )
    rows = result.all()
    logger.info(f"bulk_delete: matched {len(rows)} products to delete")
    if rows:
        matched_ids = [product.id for product, _ in rows]
        from sqlalchemy import update as _sa_update
        from datetime import datetime, timezone as _tz
        await db.execute(
            _sa_update(ProductCache)
            .where(ProductCache.id.in_(matched_ids))
            .values(is_active=False, user_deleted_at=datetime.now(_tz.utc))
        )
        await db.commit()
        # Re-fetch rows after update for 1C sync
        re_result = await db.execute(
            select(ProductCache, Store)
            .join(Store, ProductCache.store_id == Store.id)
            .where(ProductCache.id.in_(matched_ids))
        )
        rows = re_result.all()
    else:
        await db.commit()

    import asyncio as _aio
    store_integrations: dict = {}
    for product, store in rows:
        if not product.onec_id and not product.article:
            continue
        sid = str(store.id)
        if sid not in store_integrations:
            integ_r = await db.execute(
                select(Integration).where(Integration.store_id == store.id)
                .order_by(Integration.status)
            )
            store_integrations[sid] = integ_r.scalars().first()
        integration = store_integrations.get(sid)
        if integration:
            _aio.ensure_future(_mark_deleted_in_onec(
                onec_url=integration.onec_url,
                onec_username=integration.onec_username,
                onec_password_enc=integration.onec_password_encrypted,
                onec_id=product.onec_id or "",
                name=product.name,
                article=product.article or "",
            ))
    return {"deleted": len(rows)}
