import os
import uuid
from typing import List, Optional
from uuid import UUID

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
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


async def _upsert_global_product(db: AsyncSession, p: ProductCache):
    """Insert or update the shared GlobalProduct catalog entry for this barcode.
    Uses raw SQL to avoid ORM mapper validation issues. Best-effort — never propagates failures."""
    if not p.barcode or not p.barcode.strip():
        return
    try:
        from sqlalchemy import text as _text
        import uuid as _uuid
        bc = p.barcode.strip()
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
            ), {"name": p.name, "price": p.price, "pp": p.purchase_price,
                "article": p.article, "category": p.category,
                "unit": p.unit or None, "bc": bc})
        else:
            await db.execute(_text(
                "INSERT INTO global_products "
                "(id, barcode, name, price, purchase_price, article, category, unit, description) "
                "VALUES (:id, :bc, :name, :price, :pp, :article, :category, :unit, :desc)"
            ), {"id": str(_uuid.uuid4()), "bc": bc, "name": p.name,
                "price": p.price, "pp": p.purchase_price,
                "article": p.article, "category": p.category,
                "unit": p.unit or "шт", "desc": p.description})
    except Exception as exc:
        from loguru import logger
        logger.warning(f"_upsert_global_product failed for barcode={p.barcode}: {exc}")


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


@router.get("/check-barcode")
async def check_barcode_global(
    barcode: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check barcode: own stores first (raw SQL), then any other store (cross-tenant)."""
    from sqlalchemy import text as _text
    # SQLite stores UUIDs without hyphens — normalize to match
    uid = str(current_user.id).replace('-', '')

    # 1. Own stores — raw SQL, no ORM
    own = (await db.execute(_text(
        "SELECT pc.id, pc.store_id, pc.onec_id, pc.barcode, pc.name, pc.price, "
        "pc.purchase_price, pc.quantity, pc.unit, pc.article, pc.category, "
        "pc.description, pc.is_active, s.name AS store_name "
        "FROM products_cache pc "
        "JOIN stores s ON pc.store_id = s.id "
        "WHERE s.owner_id = :uid AND pc.barcode = :bc AND pc.is_active = 1 "
        "LIMIT 1"
    ), {"uid": uid, "bc": barcode})).fetchone()

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
        "WHERE s.owner_id != :uid AND pc.barcode = :bc AND pc.is_active = 1 "
        "LIMIT 1"
    ), {"uid": uid, "bc": barcode})).fetchone()

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

    return {"found": False, "product": None, "store_name": None}


@router.get("/search-global")
async def search_global_catalog(
    q: str = "",
    limit: int = 8,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search products_cache by name across ALL users (raw SQL, cross-tenant)."""
    q = q.strip()
    if len(q) < 2:
        return []
    from sqlalchemy import text as _text
    rows = (await db.execute(_text(
        "SELECT pc.barcode, pc.name, pc.price, pc.purchase_price, "
        "pc.article, pc.category, pc.unit, pc.description "
        "FROM products_cache pc "
        "JOIN stores s ON pc.store_id = s.id "
        "WHERE pc.name LIKE :q AND pc.is_active = 1 "
        "GROUP BY lower(pc.name) "
        "LIMIT :lim"
    ), {"q": f"%{q}%", "lim": limit})).fetchall()
    return [
        {"id": None, "store_id": None, "barcode": r[0], "name": r[1],
         "price": r[2], "purchase_price": r[3], "article": r[4],
         "category": r[5], "unit": r[6], "description": r[7],
         "quantity": 0, "source": "global"}
        for r in rows
    ]


@router.get("/{store_id}")
async def list_products(
    store_id: UUID,
    search: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_store_access(store_id, current_user, db)

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

    return _serialize_product(product)


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
    from backend.services.ocr_service import OCRService

    store_id_uuid = UUID(store_id)
    await _check_store_access(store_id_uuid, current_user, db)

    contents = await file.read()

    ocr_service = OCRService()
    extracted_text = ocr_service.extract_text(contents)

    ai_service = AIService()
    product_data = await ai_service.recognize_product_from_image(extracted_text, contents)

    return {"recognized": product_data, "ocr_text": extracted_text}


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
    extracted_text = ocr_service.extract_text(contents)

    ai_service = AIService()
    products = await ai_service.parse_invoice(extracted_text)

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
    await db.commit()
    await db.refresh(product)
    await _upsert_global_product(db, product)
    await db.commit()
    return _serialize_product(product)


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
    await db.commit()
    return _serialize_product(product)


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
