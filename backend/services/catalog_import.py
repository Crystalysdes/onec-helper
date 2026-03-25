"""
Catalog import service — streams CSV line-by-line, persists progress in DB.
No in-memory state: all status lives in catalog_import_jobs table.
"""
import asyncio
import csv
import os
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database.connection import AsyncSessionLocal, engine
from backend.database.models import CatalogImportJob, GlobalProduct
from backend.services.catalog_cleaner import clean_record

CATALOG_DIR = "/app/catalog"
BATCH_SIZE = 1000          # rows per DB insert
YIELD_EVERY = 500          # rows between asyncio.sleep(0)
UPDATE_DB_EVERY = 5000     # rows between job progress update in DB

# Module-level set keeps task references alive (prevents GC)
_running_tasks: set = set()


def _fire(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)
    return task


# ── helpers ──────────────────────────────────────────────────────────────────

def _find_csv_path() -> tuple[str | None, bool]:
    """Return (csv_path, is_temp). is_temp=True means caller must delete it."""
    if not os.path.exists(CATALOG_DIR):
        return None, False

    known = ("products.csv", "barcodes.csv")
    for name in known:
        p = os.path.join(CATALOG_DIR, name)
        if os.path.exists(p):
            return p, False

    csv_files = sorted(f for f in os.listdir(CATALOG_DIR) if f.endswith(".csv"))
    if csv_files:
        return os.path.join(CATALOG_DIR, csv_files[0]), False

    zip_files = sorted(f for f in os.listdir(CATALOG_DIR) if f.endswith(".zip"))
    if zip_files:
        return zip_files[0], True   # signal to extract below

    return None, False


def _extract_zip(zip_path: str) -> str:
    """Extract first CSV from ZIP into a temp file; return temp path."""
    with zipfile.ZipFile(zip_path) as zf:
        csv_name = next((n for n in zf.namelist() if n.endswith(".csv")), None)
        if not csv_name:
            raise ValueError(f"В архиве {zip_path} не найден CSV")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="wb")
        with zf.open(csv_name) as src:
            while chunk := src.read(1 << 20):  # 1 MB chunks
                tmp.write(chunk)
        tmp.close()
        logger.info(f"Extracted {csv_name} → {tmp.name}")
        return tmp.name


def _detect_encoding(path: str) -> str:
    with open(path, "rb") as f:
        sample = f.read(16_384)
    try:
        sample.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1251"


def _detect_delimiter(path: str, encoding: str) -> str:
    """Sniff CSV delimiter from first 4KB. Fallback to comma."""
    with open(path, "r", encoding=encoding, errors="replace") as f:
        sample = f.read(4096)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


async def _update_job(job_id: str, **fields):
    """Persist job progress to DB."""
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(f"UPDATE catalog_import_jobs SET {set_clause} WHERE id = :job_id"),
            {**fields, "job_id": job_id},
        )
        await db.commit()


# ── main import coroutine ─────────────────────────────────────────────────────

async def run_import(job_id: str, limit: int = 2_000_000):
    """Stream-import catalog CSV into global_products. All status in DB."""
    tmp_file = None
    loop = asyncio.get_running_loop()

    try:
        await _update_job(job_id, stage="reading")

        raw_path, is_zip_signal = _find_csv_path()
        if raw_path is None:
            raise FileNotFoundError(f"Нет CSV/ZIP файлов в {CATALOG_DIR}")

        # If we got a zip filename back, extract it
        if is_zip_signal:
            zip_path = os.path.join(CATALOG_DIR, raw_path)
            await _update_job(job_id, stage="parsing")
            tmp_file = await loop.run_in_executor(None, _extract_zip, zip_path)
            csv_path = tmp_file
        else:
            csv_path = raw_path

        encoding = await loop.run_in_executor(None, _detect_encoding, csv_path)
        delimiter = await loop.run_in_executor(None, _detect_delimiter, csv_path, encoding)
        file_name = os.path.basename(csv_path)
        await _update_job(job_id, stage="importing", file_name=file_name)
        logger.info(f"[import:{job_id[:8]}] streaming {csv_path} enc={encoding} delim={repr(delimiter)} limit={limit}")

        imported = 0
        skipped = 0
        batch: list[dict] = []

        with open(csv_path, "r", encoding=encoding, errors="replace", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=delimiter)
            # Log the header so we can verify column names
            if reader.fieldnames is None:
                next(reader, None)
            logger.info(f"[import:{job_id[:8]}] CSV columns: {reader.fieldnames}")
            for row_count, row in enumerate(reader, 1):
                if (imported + skipped) >= limit:
                    break

                if row_count % YIELD_EVERY == 0:
                    await asyncio.sleep(0)

                cleaned = clean_record(row)
                if not cleaned:
                    skipped += 1
                    continue

                batch.append({"id": uuid.uuid4(), **cleaned})

                if len(batch) >= BATCH_SIZE:
                    async with AsyncSessionLocal() as db:
                        stmt = pg_insert(GlobalProduct).values(batch)
                        stmt = stmt.on_conflict_do_nothing(index_elements=["barcode"])
                        await db.execute(stmt)
                        await db.commit()
                    imported += len(batch)
                    batch.clear()

                    if imported % UPDATE_DB_EVERY == 0:
                        await _update_job(job_id, imported=imported, skipped=skipped)
                        logger.info(f"[import:{job_id[:8]}] {imported:,} imported, {skipped:,} skipped")

        if batch:
            async with AsyncSessionLocal() as db:
                stmt = pg_insert(GlobalProduct).values(batch)
                stmt = stmt.on_conflict_do_nothing(index_elements=["barcode"])
                await db.execute(stmt)
                await db.commit()
            imported += len(batch)

        await _update_job(
            job_id,
            status="done",
            stage="done",
            imported=imported,
            skipped=skipped,
            finished_at=datetime.now(timezone.utc),
        )
        logger.info(f"[import:{job_id[:8]}] DONE — {imported:,} imported, {skipped:,} skipped")

        await _ensure_trgm_index()

    except Exception as exc:
        logger.error(f"[import:{job_id[:8]}] ERROR: {exc}", exc_info=True)
        await _update_job(
            job_id,
            status="error",
            error_message=str(exc)[:2000],
            finished_at=datetime.now(timezone.utc),
        )
    finally:
        if tmp_file and os.path.exists(tmp_file):
            os.unlink(tmp_file)


# ── start import (creates DB record + fires task) ────────────────────────────

async def start_import(limit: int = 2_000_000) -> str:
    """Create a new job record in DB, fire background task, return job_id."""
    job_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO catalog_import_jobs (id, status, stage, imported, skipped) "
                "VALUES (:id, 'running', 'reading', 0, 0)"
            ),
            {"id": job_id},
        )
        await db.commit()
    _fire(run_import(job_id, limit))
    return job_id


async def get_latest_job() -> dict | None:
    """Return the most recent import job as a dict."""
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            text("SELECT id, status, stage, imported, skipped, error_message, "
                 "started_at, finished_at, file_name "
                 "FROM catalog_import_jobs ORDER BY started_at DESC LIMIT 1")
        )).fetchone()
    if not row:
        return None
    return dict(row._mapping)


# ── trigram index ─────────────────────────────────────────────────────────────

async def _ensure_trgm_index():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("COMMIT"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_global_products_name_trgm "
                "ON global_products USING GIN (name gin_trgm_ops)"
            ))
            await conn.commit()
        logger.info("pg_trgm index ensured")
    except Exception as e:
        logger.warning(f"trgm index (non-fatal): {e}")
