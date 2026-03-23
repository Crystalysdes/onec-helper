-- Migration: create global_products table and backfill from product_cache
-- Works with SQLite (dev.db). Run via: sqlite3 dev.db < this_file.sql
-- Or open dev.db in DB Browser for SQLite and paste the statements below.

-- 1. Create the table if it doesn't exist
CREATE TABLE IF NOT EXISTS global_products (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
    barcode     TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    price       REAL,
    purchase_price REAL,
    article     TEXT,
    category    TEXT,
    unit        TEXT DEFAULT 'шт',
    description TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT
);

CREATE INDEX IF NOT EXISTS ix_global_products_barcode ON global_products (barcode);

-- 2. Backfill from existing products (skip duplicates)
INSERT OR IGNORE INTO global_products (barcode, name, price, purchase_price, article, category, unit, description)
SELECT
    barcode,
    name,
    price,
    purchase_price,
    article,
    category,
    COALESCE(unit, 'шт'),
    description
FROM product_cache
WHERE barcode IS NOT NULL
  AND barcode <> ''
GROUP BY barcode;

-- 3. Show result
SELECT COUNT(*) AS global_catalog_entries FROM global_products;
