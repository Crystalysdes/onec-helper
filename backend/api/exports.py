"""Exported-files API.

Endpoints:
    GET    /exports/formats                 — list available export formats
    POST   /exports/{format_id}             — generate a new export, store it,
                                              push an SSE event to all clients
                                              of the current user, return meta
    GET    /exports                         — list the user's stored exports
    GET    /exports/{file_id}               — metadata for one export
    GET    /exports/{file_id}/download      — download the file (bytes)
    DELETE /exports/{file_id}               — delete an export
    GET    /exports/stream                  — Server-Sent Events channel that
                                              pushes export_created / deleted
                                              events. Accepts `?token=<jwt>`
                                              since EventSource can't set
                                              Authorization headers.
"""
from __future__ import annotations

from typing import List, Optional
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import get_current_user, verify_token
from backend.database.connection import get_db, AsyncSessionLocal
from backend.database.models import ExportedFile, ProductCache, Store, User
from backend.services import event_bus
from backend.services.exports import FORMATS, get_format, list_formats


router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────
class ExportRequest(BaseModel):
    store_id: str
    # Optional override of product selection — by default we include every
    # active product in the store. When `product_ids` is provided, only those
    # IDs (belonging to the same store) are exported.
    product_ids: Optional[List[str]] = None


class ExportFileOut(BaseModel):
    id: str
    format_id: str
    format_label: str
    filename: str
    size_bytes: int
    products_count: int
    store_id: Optional[str] = None
    created_at: str


# ── Helpers ──────────────────────────────────────────────────────────────────
def _serialize(f: ExportedFile) -> ExportFileOut:
    fmt = FORMATS.get(f.format_id)
    return ExportFileOut(
        id=str(f.id),
        format_id=f.format_id,
        format_label=fmt.label if fmt else f.format_id,
        filename=f.filename,
        size_bytes=f.size_bytes,
        products_count=f.products_count,
        store_id=str(f.store_id) if f.store_id else None,
        created_at=f.created_at.isoformat() if f.created_at else "",
    )


def _product_to_dict(p: ProductCache) -> dict:
    return {
        "name": p.name or "",
        "barcode": p.barcode or "",
        "article": p.article or "",
        "unit": p.unit or "шт",
        "category": p.category or "",
        "price": p.price,
        "purchase_price": p.purchase_price,
        "quantity": p.quantity or 0,
        "description": p.description or "",
    }


async def _ensure_store_access(store_id: UUID, user: User, db: AsyncSession) -> Store:
    r = await db.execute(
        select(Store).where(Store.id == store_id, Store.owner_id == user.id)
    )
    store = r.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Магазин не найден")
    return store


# ── Format catalogue ─────────────────────────────────────────────────────────
@router.get("/formats")
async def formats(current_user: User = Depends(get_current_user)):
    return {"formats": list_formats()}


# ── Generate a new export ────────────────────────────────────────────────────
@router.post("/{format_id}", status_code=status.HTTP_201_CREATED, response_model=ExportFileOut)
async def create_export(
    format_id: str,
    payload: ExportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Validate format
    try:
        fmt = get_format(format_id)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Неизвестный формат: {format_id}")

    # 2. Validate store ownership
    try:
        store_uuid = UUID(payload.store_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Некорректный store_id")
    store = await _ensure_store_access(store_uuid, current_user, db)

    # 3. Load products
    q = (
        select(ProductCache)
        .where(ProductCache.store_id == store_uuid, ProductCache.is_active == True)  # noqa: E712
        .where(ProductCache.user_deleted_at.is_(None))
    )
    if payload.product_ids:
        try:
            ids = [UUID(pid) for pid in payload.product_ids]
        except ValueError:
            raise HTTPException(status_code=400, detail="Некорректный product_ids")
        q = q.where(ProductCache.id.in_(ids))

    result = await db.execute(q.order_by(ProductCache.name.asc()))
    products = result.scalars().all()
    if not products:
        raise HTTPException(
            status_code=400,
            detail="В магазине нет товаров для экспорта",
        )

    rows = [_product_to_dict(p) for p in products]

    # 4. Build the file
    try:
        data = fmt.generate(rows)
    except Exception as exc:
        logger.exception("Export generation failed")
        raise HTTPException(status_code=500, detail=f"Ошибка генерации файла: {exc}")

    filename = fmt.default_filename(store_name=store.name)

    # 5. Persist
    ef = ExportedFile(
        user_id=current_user.id,
        store_id=store.id,
        format_id=fmt.format_id,
        filename=filename,
        content_type=fmt.content_type,
        size_bytes=len(data),
        products_count=len(rows),
        data=data,
        extra_meta={"store_name": store.name, "format_label": fmt.label},
    )
    db.add(ef)
    await db.flush()
    await db.refresh(ef)

    out = _serialize(ef)

    # 6. Fan out event to connected clients (web / desktop) of this user
    try:
        await event_bus.publish(
            current_user.id,
            "export_created",
            out.model_dump(),
        )
    except Exception as e:
        logger.warning(f"event_bus publish failed: {e}")

    return out


# ── List / read / download / delete ──────────────────────────────────────────
@router.get("", response_model=List[ExportFileOut])
@router.get("/", response_model=List[ExportFileOut])
async def list_exports(
    store_id: Optional[str] = None,
    format_id: Optional[str] = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(ExportedFile).where(ExportedFile.user_id == current_user.id)
    if store_id:
        try:
            q = q.where(ExportedFile.store_id == UUID(store_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Некорректный store_id")
    if format_id:
        q = q.where(ExportedFile.format_id == format_id)
    q = q.order_by(ExportedFile.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [_serialize(f) for f in rows]


@router.get("/{file_id}", response_model=ExportFileOut)
async def get_export(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        fid = UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Некорректный id")
    r = await db.execute(
        select(ExportedFile).where(
            and_(ExportedFile.id == fid, ExportedFile.user_id == current_user.id)
        )
    )
    ef = r.scalar_one_or_none()
    if not ef:
        raise HTTPException(status_code=404, detail="Файл не найден")
    return _serialize(ef)


@router.get("/{file_id}/download")
async def download_export(
    file_id: str,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Download a previously generated Excel file.

    Accepts either an Authorization header (standard) or `?token=<jwt>` for
    browser-initiated downloads that can't set headers (e.g. `<a download>`).
    """
    user = await _auth_from_header_or_token(db, token)
    try:
        fid = UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Некорректный id")
    r = await db.execute(
        select(ExportedFile).where(
            and_(ExportedFile.id == fid, ExportedFile.user_id == user.id)
        )
    )
    ef = r.scalar_one_or_none()
    if not ef:
        raise HTTPException(status_code=404, detail="Файл не найден")

    # Safely encode the filename for the Content-Disposition header — it may
    # contain Cyrillic characters.
    ascii_name = ef.filename.encode("ascii", "ignore").decode() or "export.xlsx"
    disp = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(ef.filename)}"
    return Response(
        content=ef.data,
        media_type=ef.content_type,
        headers={"Content-Disposition": disp},
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_export(
    file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        fid = UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Некорректный id")
    r = await db.execute(
        select(ExportedFile).where(
            and_(ExportedFile.id == fid, ExportedFile.user_id == current_user.id)
        )
    )
    ef = r.scalar_one_or_none()
    if not ef:
        raise HTTPException(status_code=404, detail="Файл не найден")
    await db.delete(ef)
    await db.flush()

    try:
        await event_bus.publish(
            current_user.id, "export_deleted", {"id": str(fid)}
        )
    except Exception as e:
        logger.warning(f"event_bus publish failed: {e}")

    return Response(status_code=204)


# ── Server-Sent Events channel ───────────────────────────────────────────────
@router.get("/stream")
async def exports_stream(
    request: Request,
    token: Optional[str] = Query(None),
):
    """Long-lived SSE connection that pushes export_created/deleted events.

    `EventSource` in browsers can't set Authorization headers, so we accept
    the JWT via query string (HTTPS-only; transmitted in logs no more than a
    normal bearer token). Desktop clients should use the same query-param
    pattern for consistency.
    """
    async with AsyncSessionLocal() as db:
        user = await _auth_from_header_or_token(db, token, request=request)

    async def event_source():
        async for chunk in event_bus.sse_stream(user.id):
            # Abort if the client went away
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx proxy buffering
        },
    )


# ── Auth fallback (Header or ?token=) ────────────────────────────────────────
async def _auth_from_header_or_token(
    db: AsyncSession,
    token: Optional[str],
    request: Optional[Request] = None,
) -> User:
    """Resolve the current user from either the Authorization header
    (Bearer <jwt>) or a `token` query param (used when the client cannot
    set headers — SSE, `<a download>`).
    """
    jwt_token: Optional[str] = token
    if not jwt_token and request is not None:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            jwt_token = auth.split(None, 1)[1].strip()
    if not jwt_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не авторизован",
        )
    payload = verify_token(jwt_token)
    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен",
        )
    try:
        user_id = UUID(payload["sub"])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")
    r = await db.execute(select(User).where(User.id == user_id))
    user = r.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Не авторизован")
    return user
