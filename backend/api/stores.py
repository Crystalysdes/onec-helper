import asyncio
import re as _re
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, not_

from backend.database.connection import get_db, AsyncSessionLocal
from backend.database.models import User, Store, Integration, IntegrationStatus, ProductCache
from backend.core.security import get_current_user, encrypt_password, decrypt_password

router = APIRouter()


def _normalize_onec_url(raw: str) -> str:
    """Normalise various 1C URL inputs to a canonical base URL.

    Accepted formats:
      - Full browser URL: https://msk1.1cfresh.com/a/sbm/3941876/ru/
      - URL without locale: https://msk1.1cfresh.com/a/sbm/3941876
      - Server + code:  msk1/3941876  or  msk2:3941876
      - Pure app code:  3941876  (defaults to msk1.1cfresh.com)
      - Local URL:      http://192.168.1.10/base
    """
    raw = raw.strip().rstrip('/')
    if not raw:
        return raw

    if raw.startswith('http://') or raw.startswith('https://'):
        raw = _re.sub(r'/[a-z]{2}(_[A-Z]{2})?/?$', '', raw)
        return raw.rstrip('/')

    if _re.match(r'^\d+$', raw):
        return f'https://msk1.1cfresh.com/a/sbm/{raw}'

    m = _re.match(r'^([a-z0-9-]+)[/:]+([0-9]+)$', raw, _re.I)
    if m:
        return f'https://{m.group(1)}.1cfresh.com/a/sbm/{m.group(2)}'

    if not raw.startswith('http'):
        return 'https://' + raw

    return raw


class StoreCreate(BaseModel):
    name: str
    description: Optional[str] = None


class StoreUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class IntegrationCreate(BaseModel):
    onec_url: str
    onec_username: str
    onec_password: str
    name: Optional[str] = "1C Integration"
    use_accounting: bool = False  # True = require debit account in bookkeeping journal


class IntegrationUpdate(BaseModel):
    onec_url: Optional[str] = None
    onec_username: Optional[str] = None
    onec_password: Optional[str] = None
    name: Optional[str] = None
    use_accounting: Optional[bool] = None
    status: Optional[str] = None  # "active" | "inactive"


@router.get("/")
async def list_stores(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Store).where(Store.owner_id == current_user.id)
    )
    stores = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "description": s.description,
            "is_active": s.is_active,
            "created_at": s.created_at,
        }
        for s in stores
    ]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_store(
    payload: StoreCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    store = Store(
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
    )
    db.add(store)
    await db.flush()
    return {"id": str(store.id), "name": store.name, "description": store.description}


@router.get("/{store_id}")
async def get_store(
    store_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Store).where(Store.id == store_id, Store.owner_id == current_user.id)
    )
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Магазин не найден")

    integrations_result = await db.execute(
        select(Integration).where(Integration.store_id == store_id)
    )
    integrations = integrations_result.scalars().all()

    return {
        "id": str(store.id),
        "name": store.name,
        "description": store.description,
        "is_active": store.is_active,
        "created_at": store.created_at,
        "integrations": [
            {
                "id": str(i.id),
                "name": i.name,
                "use_accounting": (i.settings or {}).get("use_accounting", True),
                "onec_url": i.onec_url,
                "onec_username": i.onec_username,
                "status": i.status,
                "last_sync_at": i.last_sync_at,
            }
            for i in integrations
        ],
    }


@router.put("/{store_id}")
async def update_store(
    store_id: UUID,
    payload: StoreUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Store).where(Store.id == store_id, Store.owner_id == current_user.id)
    )
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Магазин не найден")

    if payload.name is not None:
        store.name = payload.name
    if payload.description is not None:
        store.description = payload.description
    if payload.is_active is not None:
        store.is_active = payload.is_active

    return {"id": str(store.id), "name": store.name}


@router.delete("/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_store(
    store_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Store).where(Store.id == store_id, Store.owner_id == current_user.id)
    )
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Магазин не найден")
    await db.delete(store)
    await db.commit()


@router.post("/{store_id}/integrations", status_code=status.HTTP_201_CREATED)
async def create_integration(
    store_id: UUID,
    payload: IntegrationCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Store).where(Store.id == store_id, Store.owner_id == current_user.id)
    )
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Магазин не найден")

    integration = Integration(
        store_id=store_id,
        name=payload.name,
        onec_url=_normalize_onec_url(payload.onec_url),
        onec_username=payload.onec_username,
        onec_password_encrypted=encrypt_password(payload.onec_password),
        status=IntegrationStatus.inactive,
        settings={"use_accounting": payload.use_accounting},
    )
    db.add(integration)
    await db.flush()
    integration_id = integration.id
    background_tasks.add_task(_run_sync_in_background, store_id, integration_id)
    return {
        "id": str(integration.id),
        "name": integration.name,
        "status": integration.status,
        "message": "Интеграция создана. Импорт товаров из 1С запущен в фоне.",
    }


@router.put("/{store_id}/integrations/{integration_id}")
async def update_integration(
    store_id: UUID,
    integration_id: UUID,
    payload: IntegrationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Store).where(Store.id == store_id, Store.owner_id == current_user.id)
    )
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Магазин не найден")

    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id, Integration.store_id == store_id
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Интеграция не найдена")

    if payload.onec_url is not None:
        integration.onec_url = _normalize_onec_url(payload.onec_url)
    if payload.onec_username is not None:
        integration.onec_username = payload.onec_username
    if payload.onec_password is not None:
        integration.onec_password_encrypted = encrypt_password(payload.onec_password)
    if payload.name is not None:
        integration.name = payload.name
    if payload.use_accounting is not None:
        s = dict(integration.settings or {})
        s["use_accounting"] = payload.use_accounting
        integration.settings = s
    if payload.status is not None:
        try:
            integration.status = IntegrationStatus(payload.status)
        except ValueError:
            pass

    await db.commit()
    await db.refresh(integration)
    return {
        "id": str(integration.id),
        "name": integration.name,
        "status": integration.status.value if integration.status else "inactive",
        "use_accounting": (integration.settings or {}).get("use_accounting", True),
    }


@router.delete("/{store_id}/integrations/{integration_id}", status_code=204)
async def delete_integration(
    store_id: UUID,
    integration_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Store).where(Store.id == store_id, Store.owner_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Магазин не найден")

    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id, Integration.store_id == store_id
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Интеграция не найдена")

    await db.delete(integration)
    await db.commit()


@router.post("/{store_id}/integrations/{integration_id}/test")
async def test_integration(
    store_id: UUID,
    integration_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.integrations.onec_integration import OneCClient

    result = await db.execute(
        select(Store).where(Store.id == store_id, Store.owner_id == current_user.id)
    )
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Магазин не найден")

    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id, Integration.store_id == store_id
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Интеграция не найдена")

    client = OneCClient(
        url=integration.onec_url,
        username=integration.onec_username,
        password=decrypt_password(integration.onec_password_encrypted),
    )
    success, message = await client.test_connection()

    integration.status = IntegrationStatus.active if success else IntegrationStatus.error
    return {"success": success, "message": message}


async def _run_sync_in_background(store_id: UUID, integration_id: UUID):
    """Pull all products + stock balances from 1C into products_cache. Runs in background."""
    from backend.integrations.onec_integration import OneCClient
    from backend.api.products import _upsert_global_product
    from loguru import logger

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Integration).where(Integration.id == integration_id)
            )
            integration = result.scalar_one_or_none()
            if not integration:
                return

            client = OneCClient(
                url=integration.onec_url,
                username=integration.onec_username,
                password=decrypt_password(integration.onec_password_encrypted),
            )

            # ── Step 1: sync products (name, article, onec_id) ──
            offset = 0
            batch = 200
            total_added = 0
            total_updated = 0
            onec_id_to_product: dict[str, ProductCache] = {}

            while True:
                success, products_1c = await client.get_products(limit=batch, offset=offset)
                if not success or not products_1c:
                    break

                for p1c in products_1c:
                    onec_id = p1c.get("onec_id")
                    name = p1c.get("name", "").strip()
                    if not name or not onec_id:
                        continue

                    existing = await db.execute(
                        select(ProductCache).where(
                            ProductCache.store_id == store_id,
                            ProductCache.onec_id == onec_id,
                        )
                    )
                    product = existing.scalar_one_or_none()

                    if product:
                        product.name = name
                        product.article = p1c.get("article") or product.article
                        product.synced_at = datetime.now(timezone.utc)
                        product.is_active = True
                        total_updated += 1
                    else:
                        product = ProductCache(
                            store_id=store_id,
                            onec_id=onec_id,
                            name=name,
                            article=p1c.get("article"),
                            synced_at=datetime.now(timezone.utc),
                        )
                        db.add(product)
                        total_added += 1

                    onec_id_to_product[str(onec_id)] = product

                await db.flush()
                if len(products_1c) < batch:
                    break
                offset += batch

            # ── Step 2: fetch barcodes and attach to products ──
            barcodes = await client.get_barcodes()
            if barcodes:
                for oid, bc in barcodes.items():
                    prod = onec_id_to_product.get(str(oid))
                    if prod and bc:
                        prod.barcode = bc
                await db.flush()
                logger.info(f"1C sync: matched {sum(1 for p in onec_id_to_product.values() if p.barcode)} barcodes")

            # ── Step 3: sync stock balances (quantities) ──
            qty_success, balances = await client.get_stock_balances()
            if qty_success and balances:
                for bal in balances:
                    oid = str(bal.get("onec_id", ""))
                    qty = float(bal.get("quantity", 0) or 0)
                    prod = onec_id_to_product.get(oid)
                    if prod:
                        prod.quantity = qty
                logger.info(f"1C sync: updated quantities for {len(balances)} items")

            # ── Step 4: sync retail + purchase prices (single register fetch) ──
            retail_prices, purchase_prices = await client._classify_all_prices()
            matched_r = matched_p = 0
            for oid, price in retail_prices.items():
                prod = onec_id_to_product.get(str(oid))
                if prod and price:
                    prod.price = float(price)
                    matched_r += 1
            for oid, price in purchase_prices.items():
                prod = onec_id_to_product.get(str(oid))
                if prod and price:
                    prod.purchase_price = float(price)
                    matched_p += 1
            logger.info(f"1C sync: prices retail={matched_r} purchase={matched_p}")

            await db.flush()

            # ── Step 5: deactivate products removed in 1C (DeletionMark) ──
            # Only touch products that were previously synced (synced_at IS NOT NULL).
            # Products created manually (synced_at=NULL) are protected — their onec_id
            # may not have propagated to 1C's OData listing yet.
            synced_ids = set(onec_id_to_product.keys())
            if synced_ids:
                to_deactivate = (await db.execute(
                    select(ProductCache).where(
                        ProductCache.store_id == store_id,
                        ProductCache.onec_id.isnot(None),
                        ProductCache.synced_at.isnot(None),
                        not_(ProductCache.onec_id.in_(synced_ids)),
                        ProductCache.is_active == True,
                    )
                )).scalars().all()
                for p in to_deactivate:
                    p.is_active = False
                if to_deactivate:
                    logger.info(f"1C sync: deactivated {len(to_deactivate)} removed products")
                await db.flush()

                # Remove from global catalog barcodes no longer active in ANY store
                dead_barcodes = [p.barcode for p in to_deactivate if p.barcode]
                if dead_barcodes:
                    from sqlalchemy import text as _text
                    await db.execute(_text("""
                        DELETE FROM global_products
                        WHERE barcode = ANY(:bcs)
                        AND NOT EXISTS (
                            SELECT 1 FROM products_cache
                            WHERE barcode = global_products.barcode
                              AND is_active = true
                        )
                    """), {"bcs": dead_barcodes})
                    logger.info(f"1C sync: cleaned up to {len(dead_barcodes)} orphaned global_products entries")

            # ── Step 6: push products to global catalog ──
            for product in onec_id_to_product.values():
                if product.barcode:
                    await _upsert_global_product(db, product)

            integration.last_sync_at = datetime.now(timezone.utc)
            integration.status = IntegrationStatus.active
            await db.commit()
            logger.info(f"1C sync done: store={store_id} added={total_added} updated={total_updated}")

        except Exception as e:
            await db.rollback()
            logger.error(f"1C sync error: {e}")


@router.post("/{store_id}/integrations/{integration_id}/sync")
async def sync_from_onec(
    store_id: UUID,
    integration_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import all products from 1C into the bot's database."""
    result = await db.execute(
        select(Store).where(Store.id == store_id, Store.owner_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Магазин не найден")

    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id, Integration.store_id == store_id
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Интеграция не найдена")

    background_tasks.add_task(_run_sync_in_background, store_id, integration_id)
    return {"status": "sync_started", "message": "Импорт товаров из 1С запущен в фоне"}


@router.get("/{store_id}/integrations/{integration_id}/stock")
async def get_onec_stock(
    store_id: UUID,
    integration_id: UUID,
    low_stock_threshold: float = 5.0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get stock balances from 1C, optionally filter low-stock items."""
    from backend.integrations.onec_integration import OneCClient

    result = await db.execute(
        select(Store).where(Store.id == store_id, Store.owner_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Магазин не найден")

    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id, Integration.store_id == store_id
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Интеграция не найдена")

    client = OneCClient(
        url=integration.onec_url,
        username=integration.onec_username,
        password=decrypt_password(integration.onec_password_encrypted),
    )
    success, balances = await client.get_stock_balances()
    if not success:
        raise HTTPException(status_code=502, detail="Не удалось получить остатки из 1С")

    onec_ids = [b["onec_id"] for b in balances if b.get("onec_id")]
    products_map = {}
    if onec_ids:
        rows = await db.execute(
            select(ProductCache).where(
                ProductCache.store_id == store_id,
                ProductCache.onec_id.in_(onec_ids),
            )
        )
        for p in rows.scalars().all():
            products_map[p.onec_id] = p.name

    result_items = []
    low_stock = []
    for b in balances:
        qty = b.get("quantity", 0)
        name = products_map.get(b.get("onec_id"), b.get("onec_id", "—"))
        item = {"onec_id": b.get("onec_id"), "name": name, "quantity": qty}
        result_items.append(item)
        if qty <= low_stock_threshold:
            low_stock.append(item)

    return {
        "total": len(result_items),
        "low_stock_count": len(low_stock),
        "low_stock": low_stock,
        "all": result_items,
    }


@router.get("/{store_id}/integrations/{integration_id}/diagnose")
async def diagnose_onec(
    store_id: UUID,
    integration_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return raw 1C data for debugging: entities, sample products, sample barcodes."""
    from backend.integrations.onec_integration import OneCClient

    result = await db.execute(
        select(Store).where(Store.id == store_id, Store.owner_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Магазин не найден")

    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id, Integration.store_id == store_id
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Интеграция не найдена")

    client = OneCClient(
        url=integration.onec_url,
        username=integration.onec_username,
        password=decrypt_password(integration.onec_password_encrypted),
    )

    entities = await client.get_entities()

    products_error = None
    try:
        ok_products, products = await client.get_products(limit=5, offset=0)
        if not ok_products:
            products_error = await client.get_products_raw_error()
    except Exception as e:
        ok_products, products = False, []
        products_error = str(e)

    barcodes = await client.get_barcodes()

    # Count synced products in DB
    synced_count = (await db.execute(
        select(ProductCache).where(ProductCache.store_id == store_id)
    )).scalars().all()

    # Find which entities match nomenclature/catalog
    nom_entities = [e for e in entities if "Номенклатур" in e and "Catalog" in e][:10]
    barcode_entities = [e for e in entities if "Штрихкод" in e]
    price_entities   = [e for e in entities if "Цен" in e and "Register" in e]
    barcode_catalog_published = bool(barcode_entities)

    # Probe barcode+price write using first product that has an onec_id
    probe_result = None
    probe_product = next((p for p in synced_count if p.onec_id), None)
    if probe_product:
        try:
            test_bc = probe_product.barcode or "4607141232117"
            test_price = float(probe_product.price or 100.0)
            probe_result = await client.probe_barcode_price(
                probe_product.onec_id, test_bc, test_price
            )
        except Exception as e:
            probe_result = {"error": str(e)}

    return {
        "entities_published": len(entities),
        "entities": entities[:30],
        "nom_entities": nom_entities,
        "barcode_catalog_published": barcode_catalog_published,
        "products_ok": ok_products,
        "products_sample": products[:5],
        "products_error": products_error,
        "barcodes_fetched": len(barcodes),
        "barcodes_sample": dict(list(barcodes.items())[:5]),
        "synced_in_db": len(synced_count),
        "synced_with_barcode": sum(1 for p in synced_count if p.barcode),
        "barcode_entities": barcode_entities,
        "price_entities": price_entities,
        "probe_barcode_price": probe_result,
    }


@router.get("/edo-check")
async def edo_check(
    internal_token: str,
    db: AsyncSession = Depends(get_db),
):
    """Internal endpoint for bot to poll EDO documents from all active integrations."""
    from backend.config import settings as backend_settings
    from backend.integrations.onec_integration import OneCClient

    if internal_token != backend_settings.SECRET_KEY[:16]:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = await db.execute(
        select(Integration, Store, User)
        .join(Store, Integration.store_id == Store.id)
        .join(User, Store.owner_id == User.id)
        .where(Integration.status == IntegrationStatus.active)
    )
    rows = result.all()

    notifications = []
    for integration, store, user in rows:
        try:
            client = OneCClient(
                url=integration.onec_url,
                username=integration.onec_username,
                password=decrypt_password(integration.onec_password_encrypted),
            )
            success, docs = await client.get_edo_documents()
            if success and docs:
                notifications.append({
                    "telegram_id": user.telegram_id,
                    "store_name": store.name,
                    "integration_id": str(integration.id),
                    "documents": docs,
                })
        except Exception as e:
            logger.warning(f"EDO check failed for integration {integration.id}: {e}")

    return {"notifications": notifications}
