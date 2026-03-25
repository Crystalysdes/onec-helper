import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

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


async def _upsert_global_product(db: AsyncSession, p: ProductCache):
    """Insert or update the shared GlobalProduct catalog entry for this barcode.
    Applies the same quality filters as catalog import.
    Uses a savepoint so any failure never corrupts the outer transaction."""
    if not p.barcode or not p.barcode.strip():
        return
    from backend.services.catalog_cleaner import (
        normalize_name, translate_category, detect_unit, _VALID_BARCODE_LENGTHS
    )
    bc = p.barcode.strip()
    # Validate standard barcode format
    if not bc.isdigit() or len(bc) not in _VALID_BARCODE_LENGTHS:
        return
    # Normalize name — reject garbage
    clean_name = normalize_name(p.name or "")
    if not clean_name:
        return
    clean_cat = translate_category(p.category) if p.category else None
    clean_unit = p.unit or detect_unit(clean_name) or "шт"
    try:
        from sqlalchemy import text as _text
        import uuid as _uuid
        async with db.begin_nested():  # savepoint — rolls back only this block on error
            row = (await db.execute(
                _text("SELECT id FROM global_products WHERE barcode = :bc LIMIT 1"), {"bc": bc}
            )).fetchone()
            if row:
                await db.execute(_text(
                    "UPDATE global_products SET "
                    "name=:name, price=COALESCE(:price, price), "
                    "purchase_price=COALESCE(:pp, purchase_price), "
                    "article=COALESCE(:article, article), "
                    "category=COALESCE(:category, category), "
                    "unit=COALESCE(:unit, unit) "
                    "WHERE barcode=:bc"
                ), {"name": clean_name, "price": p.price, "pp": p.purchase_price,
                    "article": p.article, "category": clean_cat,
                    "unit": clean_unit, "bc": bc})
            else:
                await db.execute(_text(
                    "INSERT INTO global_products "
                    "(id, barcode, name, price, purchase_price, article, category, unit, description) "
                    "VALUES (:id, :bc, :name, :price, :pp, :article, :category, :unit, :desc)"
                ), {"id": _uuid.uuid4(), "bc": bc, "name": clean_name,
                    "price": p.price, "pp": p.purchase_price,
                    "article": p.article, "category": clean_cat,
                    "unit": clean_unit, "desc": p.description})
    except Exception as exc:
        from loguru import logger
        logger.warning(f"_upsert_global_product failed for barcode={bc}: {exc}")


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


async def _push_to_onec_bg(store_id: UUID, product_id: UUID, product_name: str, product_onec_id: str | None, product_article: str | None):
    """Push a product to 1C in the background. Uses its own DB session."""
    from backend.integrations.onec_integration import OneCClient
    from backend.core.security import decrypt_password
    from backend.database.connection import AsyncSessionLocal
    from loguru import logger

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

            # Re-fetch product from DB so we can update it
            p_result = await db.execute(
                select(ProductCache).where(ProductCache.id == product_id)
            )
            product = p_result.scalar_one_or_none()
            if not product:
                return

            client = OneCClient(
                url=integration.onec_url,
                username=integration.onec_username,
                password=decrypt_password(integration.onec_password_encrypted),
            )
            if product.onec_id:
                success, data = await client.update_product(product.onec_id, product)
            else:
                success, data = await client.create_product(product)
                if success and data and data.get("Ref_Key"):
                    product.onec_id = data["Ref_Key"]

            if success:
                product.synced_at = datetime.now(timezone.utc)
                await db.commit()
                logger.info(f"Product '{product.name}' synced to 1C (onec_id={product.onec_id})")
            else:
                logger.warning(f"1C push failed for '{product.name}': {data}")
        except Exception as e:
            logger.error(f"_push_to_onec_bg error: {e}")


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
        "FROM global_products WHERE barcode = :bc LIMIT 1"
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
    """Search GlobalProduct catalog + products_cache cross-tenant by name."""
    q = q.strip()
    if len(q) < 2:
        return []
    from sqlalchemy import text as _text

    # 1. Search GlobalProduct (Open Food Facts catalog)
    gp_rows = (await db.execute(_text(
        "SELECT barcode, name, price, purchase_price, article, category, unit, description "
        "FROM global_products "
        "WHERE lower(name) LIKE lower(:q) "
        "ORDER BY name LIMIT :lim"
    ), {"q": f"%{q}%", "lim": limit})).fetchall()

    results = [
        {"id": None, "store_id": None, "barcode": r[0], "name": r[1],
         "price": r[2], "purchase_price": r[3], "article": r[4],
         "category": r[5], "unit": r[6], "description": r[7],
         "quantity": 0, "source": "catalog"}
        for r in gp_rows
    ]

    # 2. Fill remaining slots from products_cache (other users)
    remaining = limit - len(results)
    if remaining > 0:
        seen_names = {r["name"].lower() for r in results}
        pc_rows = (await db.execute(_text(
            "SELECT DISTINCT pc.barcode, pc.name, pc.price, pc.purchase_price, "
            "pc.article, pc.category, pc.unit, pc.description "
            "FROM products_cache pc "
            "WHERE lower(pc.name) LIKE lower(:q) AND pc.is_active = :active "
            "LIMIT :lim"
        ), {"q": f"%{q}%", "lim": remaining * 2, "active": True})).fetchall()
        for r in pc_rows:
            if r[1].lower() not in seen_names:
                results.append({
                    "id": None, "store_id": None, "barcode": r[0], "name": r[1],
                    "price": r[2], "purchase_price": r[3], "article": r[4],
                    "category": r[5], "unit": r[6], "description": r[7],
                    "quantity": 0, "source": "user_catalog"
                })
                seen_names.add(r[1].lower())
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
    background_tasks: BackgroundTasks,
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

    await _upsert_global_product(db, product)

    log = Log(
        user_id=current_user.id,
        store_id=store_id,
        level=LogLevel.info,
        action="product_created",
        message=f"Создан товар: {payload.name}",
        meta={"product_id": str(product.id)},
    )
    db.add(log)
    result = _serialize_product(product)
    background_tasks.add_task(
        _push_to_onec_bg, store_id, product.id, product.name, product.onec_id, product.article
    )
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

    store_id_uuid = UUID(store_id)
    await _check_store_access(store_id_uuid, current_user, db)

    contents = await file.read()

    # Compress image to max 800px before sending to AI (reduces payload ~10x)
    import asyncio
    compressed = await asyncio.get_event_loop().run_in_executor(
        None, _compress_image, contents, 800
    )

    ai_service = AIService()
    product_data = await ai_service.recognize_product_from_image("", compressed)

    return {"recognized": product_data, "ocr_text": ""}


@router.post("/upload-invoice")
async def upload_invoice(
    store_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.ai_service import AIService
    from backend.services.ocr_service import OCRService

    store_id_uuid = UUID(store_id)
    await _check_store_access(store_id_uuid, current_user, db)

    contents = await file.read()
    filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(contents)

    ocr_service = OCRService()
    content_type = file.content_type or "image/jpeg"
    extracted_text = ocr_service.extract_from_file(contents, content_type)

    ai_service = AIService()
    if extracted_text.strip():
        products = await ai_service.parse_invoice(extracted_text)
    else:
        products = await ai_service.parse_invoice_from_image(contents)

    log = Log(
        user_id=current_user.id,
        store_id=store_id_uuid,
        level=LogLevel.info,
        action="invoice_uploaded",
        message=f"Загружена накладная: {file.filename}",
        meta={"filename": filename, "products_found": len(products)},
    )
    db.add(log)

    return {
        "filename": file.filename,
        "ocr_text": extracted_text,
        "products": products,
        "count": len(products),
    }


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
    await _upsert_global_product(db, product)
    result = _serialize_product(product)
    await db.commit()
    # 1C push runs in background — does not block response
    import asyncio
    asyncio.ensure_future(_push_to_onec_bg(UUID(store_id), product.id, product.name, product.onec_id, product.article))
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

    await _upsert_global_product(db, product)
    result = _serialize_product(product)
    await db.commit()
    background_tasks.add_task(
        _push_to_onec_bg, product.store_id, product.id, product.name, product.onec_id, product.article
    )
    return result


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
    product.is_active = False
    await db.commit()


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
            await _upsert_global_product(db, p)
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
    for product, _ in rows:
        product.is_active = False
    await db.commit()
    return {"deleted": len(rows)}
