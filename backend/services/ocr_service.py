import io
from typing import Optional
from loguru import logger

try:
    import pytesseract
    from PIL import Image
    import cv2
    import numpy as np
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False
    logger.warning("pytesseract/cv2/numpy not available — OCR disabled")


class OCRService:
    def __init__(self):
        if _OCR_AVAILABLE:
            pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

    def _preprocess_image(self, image):
        """Preprocess image for better OCR accuracy."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = np.ones((1, 1), np.uint8)
        processed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        return processed

    def extract_text(self, image_bytes: bytes) -> str:
        """Extract text from image bytes using Tesseract OCR."""
        if not _OCR_AVAILABLE:
            return ""
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                pil_image = Image.open(io.BytesIO(image_bytes))
                img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

            processed = self._preprocess_image(img)
            pil_processed = Image.fromarray(processed)

            text = pytesseract.image_to_string(
                pil_processed,
                lang="rus+eng",
                config="--psm 6 --oem 3",
            )
            return text.strip()
        except Exception as e:
            logger.error(f"OCR extraction error: {e}")
            return ""

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF document."""
        try:
            import fitz
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            texts = []
            for page in doc:
                text = page.get_text()
                if text.strip():
                    texts.append(text)
                else:
                    pix = page.get_pixmap(dpi=200)
                    img_bytes = pix.tobytes("png")
                    texts.append(self.extract_text(img_bytes))
            return "\n".join(texts)
        except ImportError:
            logger.warning("PyMuPDF not installed, falling back to image OCR")
            return self.extract_text(pdf_bytes)
        except Exception as e:
            logger.error(f"PDF OCR error: {e}")
            return ""

    def extract_from_file(self, file_bytes: bytes, content_type: str) -> str:
        """Auto-detect and extract text from any supported file type."""
        if "pdf" in content_type:
            return self.extract_text_from_pdf(file_bytes)
        elif content_type in ("image/jpeg", "image/png", "image/bmp", "image/tiff", "image/webp"):
            return self.extract_text(file_bytes)
        else:
            return self.extract_text(file_bytes)
