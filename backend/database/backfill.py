"""Startup data migrations / backfills."""
import uuid as _uuid
from loguru import logger
from sqlalchemy import text

from backend.database.connection import AsyncSessionLocal
from backend.services.catalog_cleaner import normalize_name, translate_category, detect_unit, _VALID_BARCODE_LENGTHS


async def backfill_global_products() -> None:
    """
    Sync every products_cache row that has a barcode into global_products.
    Uses raw SQL to avoid triggering SQLAlchemy ORM mapper validation.
    Safe to call at any time — creates the table if it doesn't exist yet.
    """
    from backend.database.connection import init_db
    await init_db()          # creates global_products table if missing

    async with AsyncSessionLocal() as db:
        try:
            # Fetch products with barcodes using raw SQL (avoids ORM mapper issues)
            rows = (await db.execute(text(
                "SELECT barcode, name, price, purchase_price, article, category, unit, description "
                "FROM products_cache "
                "WHERE barcode IS NOT NULL AND barcode != '' AND is_active = true"
            ))).fetchall()

            if not rows:
                logger.info("backfill_global_products: nothing to migrate")
                return

            # Deduplicate by barcode — prefer row with price
            seen: dict[str, tuple] = {}
            for row in rows:
                bc = row[0].strip()
                if not bc:
                    continue
                if bc not in seen or (seen[bc][2] is None and row[2] is not None):
                    seen[bc] = row

            # Fetch already-existing barcodes AND names (for name-level dedup)
            gp_rows = (await db.execute(
                text("SELECT barcode, lower(name) FROM global_products")
            )).fetchall()
            existing_barcodes = {r[0] for r in gp_rows}
            existing_names = {r[1] for r in gp_rows}

            new_entries = 0
            skipped = 0
            for bc, row in seen.items():
                if bc in existing_barcodes:
                    continue
                # Only valid EAN barcodes — skip article-only / test products
                if not bc.isdigit() or len(bc) not in _VALID_BARCODE_LENGTHS:
                    skipped += 1
                    continue
                clean_name = normalize_name(row[1] or "")
                if not clean_name or len(clean_name) < 3:
                    skipped += 1
                    continue
                # Skip if a different barcode already carries this name (name dedup)
                if clean_name.lower() in existing_names:
                    skipped += 1
                    continue
                clean_cat = translate_category(row[5]) if row[5] else None
                clean_unit = row[6] or detect_unit(clean_name) or "шт"
                await db.execute(text(
                    "INSERT INTO global_products "
                    "(id, barcode, name, price, purchase_price, article, category, unit, description) "
                    "VALUES (:id, :barcode, :name, :price, :purchase_price, :article, :category, :unit, :description)"
                ), {
                    "id": str(_uuid.uuid4()),
                    "barcode": bc,
                    "name": clean_name,
                    "price": row[2],
                    "purchase_price": row[3],
                    "article": row[4],
                    "category": clean_cat,
                    "unit": clean_unit,
                    "description": row[7],
                })
                new_entries += 1

            await db.commit()
            logger.info(
                f"backfill_global_products: added {new_entries}, skipped {skipped} "
                f"({len(rows)} products_cache rows scanned, "
                f"{len(existing)} already existed)"
            )
        except Exception as exc:
            logger.error(f"backfill_global_products failed: {exc}")
            await db.rollback()
