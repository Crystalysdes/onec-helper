"""Base class for Excel export formats."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, TypedDict


class ProductDict(TypedDict, total=False):
    """Shape of a single product row passed into a format generator.

    All fields are optional; individual formats decide which ones they use.
    """
    name: str
    barcode: str
    article: str
    unit: str
    category: str
    category_l2: str
    category_l3: str
    price: float
    purchase_price: float
    quantity: float
    vat_rate: int
    product_type: str          # "Товар" / "Услуга" / "Весовой товар"
    description: str


class ExportFormat(ABC):
    """Describes one export format (e.g. Kontur.Market, 1С:Розница).

    Subclasses override the class attributes and implement `generate`.
    """
    # Short identifier used in URLs / API (e.g. "kontur_market").
    format_id: str = ""
    # Human-readable label.
    label: str = ""
    # Longer description shown in UI.
    description: str = ""
    # File extension (with dot), e.g. ".xlsx".
    extension: str = ".xlsx"
    # MIME type.
    content_type: str = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    # Coarse grouping for UI (e.g. "kontur" / "onec").
    target: str = ""

    @abstractmethod
    def generate(self, products: List[ProductDict], meta: Dict[str, Any] | None = None) -> bytes:
        """Build the file and return its bytes."""
        raise NotImplementedError

    # ── helpers ---------------------------------------------------------------
    @staticmethod
    def safe_str(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def safe_num(value: Any, default: float | None = None) -> float | None:
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def default_filename(self, store_name: str | None = None) -> str:
        """Suggested filename for this export (without path)."""
        from datetime import datetime
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        store = f"_{store_name}" if store_name else ""
        # Sanitise for filesystem
        import re
        store = re.sub(r"[^\w\-]+", "_", store)[:40]
        return f"{self.format_id}_{stamp}{store}{self.extension}"
