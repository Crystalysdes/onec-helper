from .ai_service import AIService
from .cache_service import CacheService

try:
    from .ocr_service import OCRService
except Exception:
    class OCRService:  # type: ignore
        def extract_text(self, *a, **kw): return ""
        def extract_from_file(self, *a, **kw): return ""

try:
    from .barcode_service import BarcodeService
except Exception:
    class BarcodeService:  # type: ignore
        def decode(self, *a, **kw): return []

__all__ = ["AIService", "OCRService", "BarcodeService", "CacheService"]
