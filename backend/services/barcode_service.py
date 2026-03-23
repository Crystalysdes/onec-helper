import io
from typing import List, Optional
from loguru import logger

try:
    import cv2
    import numpy as np
    from pyzbar import pyzbar
    from PIL import Image
    _BARCODE_AVAILABLE = True
except (ImportError, Exception):
    _BARCODE_AVAILABLE = False
    logger.warning("cv2/pyzbar not available — barcode decoding disabled")


class BarcodeService:
    def decode(self, image_bytes: bytes) -> List[str]:
        """Decode barcodes from image bytes."""
        if not _BARCODE_AVAILABLE:
            return []
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                pil_image = Image.open(io.BytesIO(image_bytes))
                img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

            results = self._decode_image(img)
            if results:
                return results

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            results = self._decode_image(gray)
            if results:
                return results

            resized = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            results = self._decode_image(resized)
            if results:
                return results

            return []
        except Exception as e:
            logger.error(f"Barcode decode error: {e}")
            return []

    def _decode_image(self, img) -> List[str]:
        """Attempt to decode barcodes from a numpy image array."""
        try:
            if len(img.shape) == 3:
                pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            else:
                pil_img = Image.fromarray(img)

            decoded = pyzbar.decode(pil_img)
            return [d.data.decode("utf-8") for d in decoded if d.data]
        except Exception as e:
            logger.debug(f"Barcode decode attempt failed: {e}")
            return []

    def generate_barcode_image(self, barcode: str, barcode_type: str = "EAN13") -> bytes:
        """Generate barcode image from string."""
        try:
            import barcode as python_barcode
            from barcode.writer import ImageWriter

            cls = python_barcode.get_barcode_class(barcode_type.lower())
            rv = io.BytesIO()
            cls(barcode, writer=ImageWriter()).write(rv)
            return rv.getvalue()
        except Exception as e:
            logger.error(f"Barcode generation error: {e}")
            return b""
