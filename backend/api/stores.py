from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database.connection import get_db
from backend.database.models import User, Store, Integration, IntegrationStatus
from backend.core.security import get_current_user, encrypt_password, decrypt_password

router = APIRouter()


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


class IntegrationUpdate(BaseModel):
    onec_url: Optional[str] = None
    onec_username: Optional[str] = None
    onec_password: Optional[str] = None
    name: Optional[str] = None


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


@router.post("/{store_id}/integrations", status_code=status.HTTP_201_CREATED)
async def create_integration(
    store_id: UUID,
    payload: IntegrationCreate,
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
        onec_url=payload.onec_url,
        onec_username=payload.onec_username,
        onec_password_encrypted=encrypt_password(payload.onec_password),
        status=IntegrationStatus.inactive,
    )
    db.add(integration)
    await db.flush()
    return {
        "id": str(integration.id),
        "name": integration.name,
        "status": integration.status,
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
        integration.onec_url = payload.onec_url
    if payload.onec_username is not None:
        integration.onec_username = payload.onec_username
    if payload.onec_password is not None:
        integration.onec_password_encrypted = encrypt_password(payload.onec_password)
    if payload.name is not None:
        integration.name = payload.name

    return {"id": str(integration.id), "name": integration.name}


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
