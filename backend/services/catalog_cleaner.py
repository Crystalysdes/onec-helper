"""
Catalog cleaning: heuristic rules + optional AI batch cleanup.
Used for catalog.app imports and GlobalProduct normalization.
"""
import re
from typing import Optional

# ── Category translations (common catalog.app English categories → Russian) ──
_CAT_MAP = {
    "electronics": "Электроника",
    "household appliances": "Бытовая техника",
    "home appliances": "Бытовая техника",
    "tools": "Инструменты",
    "power tools": "Электроинструменты",
    "hand tools": "Ручной инструмент",
    "garden": "Сад и огород",
    "gardening": "Сад и огород",
    "plumbing": "Сантехника",
    "building materials": "Стройматериалы",
    "construction": "Стройматериалы",
    "paint": "Краски и лаки",
    "cleaning": "Бытовая химия",
    "hygiene": "Гигиена",
    "personal care": "Личная гигиена",
    "cosmetics": "Косметика",
    "health": "Здоровье",
    "pharmacy": "Аптека",
    "medicine": "Медицина",
    "food": "Продукты питания",
    "beverages": "Напитки",
    "drinks": "Напитки",
    "dairy": "Молочные продукты",
    "baby": "Товары для детей",
    "children": "Товары для детей",
    "toys": "Игрушки",
    "sports": "Спорт",
    "auto": "Автотовары",
    "automotive": "Автотовары",
    "office": "Канцтовары",
    "stationery": "Канцтовары",
    "clothing": "Одежда",
    "footwear": "Обувь",
    "shoes": "Обувь",
    "furniture": "Мебель",
    "lighting": "Освещение",
    "lamps": "Лампы",
    "cables": "Кабели и провода",
    "electrical": "Электрика",
    "packaging": "Упаковка",
    "containers": "Ёмкости и контейнеры",
    "pet": "Товары для животных",
    "pets": "Товары для животных",
    "books": "Книги",
    "software": "Программное обеспечение",
    "computer": "Компьютеры и комплектующие",
    "mobile": "Мобильные устройства",
    "phone": "Телефоны",
}

# ── Unit detection patterns ──
_UNIT_PATTERNS = [
    (re.compile(r'\b(\d+(?:[.,]\d+)?)\s*(кг|kg)\b', re.I), 'кг'),
    (re.compile(r'\b(\d+(?:[.,]\d+)?)\s*(г|гр|gr|g)\b', re.I),   'г'),
    (re.compile(r'\b(\d+(?:[.,]\d+)?)\s*(л|l|литр)\b', re.I),    'л'),
    (re.compile(r'\b(\d+(?:[.,]\d+)?)\s*(мл|ml)\b', re.I),       'мл'),
    (re.compile(r'\b(\d+(?:[.,]\d+)?)\s*(м|m)\b', re.I),         'м'),
    (re.compile(r'\b(\d+(?:[.,]\d+)?)\s*(см|cm)\b', re.I),       'см'),
    (re.compile(r'\b(\d+(?:[.,]\d+)?)\s*(мм|mm)\b', re.I),       'мм'),
    (re.compile(r'\b(\d+(?:[.,]\d+)?)\s*(шт|pcs|pc)\b', re.I),   'шт'),
    (re.compile(r'\b(\d+(?:[.,]\d+)?)\s*(упак|уп|pack|pkg)\b', re.I), 'упак'),
    (re.compile(r'\b(\d+(?:[.,]\d+)?)\s*(пар|пары|pair)\b', re.I), 'пара'),
    (re.compile(r'\b(\d+(?:[.,]\d+)?)\s*(рулон|рул|roll)\b', re.I), 'рулон'),
]

# Standard barcode lengths: EAN-8, UPC-A, EAN-13, ITF-14
_VALID_BARCODE_LENGTHS = {8, 12, 13, 14}

# ── Garbage detection ──
_GARBAGE_PATTERNS = [
    re.compile(r'^[\d\s\-_/\\.,;:]+$'),           # only digits/punctuation
    re.compile(r'^[a-z0-9]{6,}$', re.I),          # looks like a barcode/hash
]

_GARBAGE_WORDS = {'null', 'none', 'n/a', 'na', 'test', 'unknown', 'no name', 'noname',
                  'товар', 'product', 'item', 'undefined', 'не определено'}

# Characters allowed in a clean product name
_ALLOWED_CHARS_RE = re.compile(
    r'[^Ѐ-ӿa-zA-Z0-9\s\-.,()/%&«»"\'!+*#№]',
    re.UNICODE
)

# Mojibake signatures: Cyrillic uppercase R/S immediately followed by Latin-extended chars
# These appear when UTF-8 Cyrillic bytes are read as Latin-1/Windows-1252
_MOJIBAKE_RE = re.compile(
    r'[РСрс][\u00b0\u00b1\u00ab\u00bb\u00b2\u00b3\u00b5-\u00bf\u00c0-\u00ff]'
    r'|[\u0080-\u00bf]{2,}'  # multiple Latin-extended in a row
)


def _is_mojibake(text: str) -> bool:
    """Return True if text looks like encoding-corrupted (mojibake) data."""
    if not text or len(text) < 4:
        return False
    # High density of Latin-extended range chars (0x80..0xFF) = classic UTF-8 read as Latin-1
    ext = sum(1 for c in text if '\x80' <= c <= '\xff')
    if ext > max(2, len(text) * 0.15):
        return True
    # Specific mojibake two-char sequences
    if _MOJIBAKE_RE.search(text):
        return True
    return False


def translate_category(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = raw.strip()
    # OFF format: "en:dairy-products,en:cheeses,..." — pick best tag
    if ":" in s:
        for tag in s.split(","):
            tag = tag.strip()
            label = re.sub(r'^[a-z]{2}:', '', tag).replace("-", " ").strip()
            if len(label) < 3:
                continue
            lower = label.lower()
            for en, ru in _CAT_MAP.items():
                if en in lower:
                    return ru
            if re.search(r'[а-яёА-ЯЁ]', label):
                return label[:60]
            if len(label) > 3:
                return label.title()[:60]
        return None
    lower = s.lower()
    for en, ru in _CAT_MAP.items():
        if en in lower:
            return ru
    if re.search(r'[а-яёА-ЯЁ]', s):
        return s[:60]
    return s.title()[:60]


def detect_unit(name: str) -> Optional[str]:
    for pattern, unit in _UNIT_PATTERNS:
        if pattern.search(name):
            return unit
    return None


def normalize_name(name: str, vendor: str = "") -> Optional[str]:
    """Clean and normalize a product name. Returns None if it looks like garbage."""
    if not name:
        return None
    name = name.strip()

    # Strip non-allowed characters (keep Cyrillic, Latin, digits, common punctuation)
    name = _ALLOWED_CHARS_RE.sub('', name).strip()

    # Length checks
    if len(name) < 3 or len(name) > 300:
        return None

    # Lowercase check
    lower = name.lower()
    if lower in _GARBAGE_WORDS:
        return None

    # Garbage pattern checks
    for pat in _GARBAGE_PATTERNS:
        if pat.fullmatch(name):
            return None

    # Remove repeated characters (e.g. "ааааааа")
    if re.search(r'(.)\1{5,}', name):
        return None

    # Must have at least one Cyrillic OR at least 3 consecutive Latin letters (brand)
    has_cyrillic = bool(re.search(r'[А-яЁё]', name))
    has_latin_word = bool(re.search(r'[a-zA-Z]{3,}', name))
    if not has_cyrillic and not has_latin_word:
        return None

    # Reject encoding-corrupted (mojibake) names
    if _is_mojibake(name):
        return None

    # Too many digits — likely a code, not a name (max 35%)
    digit_count = sum(1 for c in name if c.isdigit())
    if digit_count > len(name) * 0.35:
        return None

    # Normalize whitespace
    name = re.sub(r'\s+', ' ', name).strip()

    # Append vendor if not already in name
    if vendor and len(vendor) > 1 and vendor.lower() not in name.lower():
        name = f"{name} {vendor}".strip()

    # Title case for fully lowercase names (Russian)
    if name == name.lower() and re.search(r'[а-яё]', name):
        name = name.capitalize()

    return name[:255]


def clean_record(row: dict) -> Optional[dict]:
    """
    Process a CSV row from catalog.app OR Open Food Facts format.
    Returns cleaned dict or None if record should be skipped.
    """
    # Barcode: OFF uses 'code', catalog.app uses 'Barcode'/'barcode'
    barcode = (row.get("code") or row.get("Barcode") or row.get("barcode") or "").strip()
    # Accept only standard barcode formats: EAN-8, UPC-A, EAN-13, ITF-14
    if not barcode or not barcode.isdigit() or len(barcode) not in _VALID_BARCODE_LENGTHS:
        return None

    # Name: OFF has product_name_ru (best), product_name (fallback); catalog.app has Name
    raw_name = (
        row.get("product_name_ru") or row.get("product_name_fr") or
        row.get("product_name") or row.get("Name") or row.get("name") or ""
    ).strip()

    # Vendor/brand
    vendor = (
        row.get("brands") or row.get("Vendor") or row.get("vendor") or ""
    ).split(",")[0].strip()

    # Article (catalog.app only)
    raw_article = (row.get("Article") or row.get("article") or "").strip()

    # Category: OFF uses categories_tags ("en:dairy,..."), catalog.app uses Category
    raw_category = (
        row.get("categories_tags") or row.get("Category") or row.get("category") or ""
    ).strip()

    name = normalize_name(raw_name, vendor)
    if not name:
        return None

    category = translate_category(raw_category) if raw_category else None
    unit = detect_unit(raw_name) or detect_unit(name) or "шт"
    article = raw_article[:60] if raw_article and re.search(r'[a-zA-Z0-9]', raw_article) else None

    return {
        "barcode": barcode,
        "name": name,
        "category": category,
        "article": article,
        "unit": unit,
    }
