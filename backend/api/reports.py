from uuid import UUID
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from backend.database.connection import get_db
from backend.database.models import User, Store, ProductCache, Log
from backend.core.security import get_current_user

router = APIRouter()


async def _check_store_access(store_id: UUID, user: User, db: AsyncSession) -> Store:
    result = await db.execute(
        select(Store).where(Store.id == store_id, Store.owner_id == user.id)
    )
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Магазин не найден")
    return store


@router.get("/{store_id}/summary")
async def get_summary(
    store_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_store_access(store_id, current_user, db)

    total_products = await db.execute(
        select(func.count(ProductCache.id)).where(
            ProductCache.store_id == store_id, ProductCache.is_active == True
        )
    )
    total = total_products.scalar()

    total_value = await db.execute(
        select(func.sum(ProductCache.price * ProductCache.quantity)).where(
            ProductCache.store_id == store_id, ProductCache.is_active == True
        )
    )
    value = total_value.scalar() or 0

    low_stock = await db.execute(
        select(func.count(ProductCache.id)).where(
            and_(
                ProductCache.store_id == store_id,
                ProductCache.is_active == True,
                ProductCache.quantity < 5,
                ProductCache.quantity >= 0,
            )
        )
    )
    low = low_stock.scalar()

    categories = await db.execute(
        select(ProductCache.category, func.count(ProductCache.id))
        .where(ProductCache.store_id == store_id, ProductCache.is_active == True)
        .group_by(ProductCache.category)
        .order_by(func.count(ProductCache.id).desc())
        .limit(10)
    )
    cats = [{"category": row[0] or "Без категории", "count": row[1]} for row in categories.all()]

    return {
        "total_products": total,
        "total_inventory_value": round(value, 2),
        "low_stock_count": low,
        "categories": cats,
    }


@router.get("/{store_id}/low-stock")
async def get_low_stock(
    store_id: UUID,
    threshold: int = 5,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_store_access(store_id, current_user, db)

    result = await db.execute(
        select(ProductCache).where(
            and_(
                ProductCache.store_id == store_id,
                ProductCache.is_active == True,
                ProductCache.quantity < threshold,
            )
        ).order_by(ProductCache.quantity)
    )
    products = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "name": p.name,
            "barcode": p.barcode,
            "quantity": p.quantity,
            "unit": p.unit,
            "price": p.price,
            "category": p.category,
        }
        for p in products
    ]


@router.get("/{store_id}/activity")
async def get_activity_log(
    store_id: UUID,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_store_access(store_id, current_user, db)

    result = await db.execute(
        select(Log)
        .where(Log.store_id == store_id)
        .order_by(Log.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()

    return [
        {
            "id": str(l.id),
            "level": l.level,
            "action": l.action,
            "message": l.message,
            "meta": l.meta,
            "created_at": l.created_at,
        }
        for l in logs
    ]


@router.get("/{store_id}/inventory")
async def get_inventory_report(
    store_id: UUID,
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_store_access(store_id, current_user, db)

    query = select(ProductCache).where(
        ProductCache.store_id == store_id, ProductCache.is_active == True
    )
    if category:
        query = query.where(ProductCache.category == category)

    result = await db.execute(query.order_by(ProductCache.name))
    products = result.scalars().all()

    total_value = sum((p.price or 0) * (p.quantity or 0) for p in products)
    total_purchase_value = sum((p.purchase_price or 0) * (p.quantity or 0) for p in products)

    return {
        "total_products": len(products),
        "total_value": round(total_value, 2),
        "total_purchase_value": round(total_purchase_value, 2),
        "potential_profit": round(total_value - total_purchase_value, 2),
        "products": [
            {
                "id": str(p.id),
                "name": p.name,
                "barcode": p.barcode,
                "category": p.category,
                "quantity": p.quantity,
                "unit": p.unit,
                "price": p.price,
                "purchase_price": p.purchase_price,
                "total_value": round((p.price or 0) * (p.quantity or 0), 2),
            }
            for p in products
        ],
    }
