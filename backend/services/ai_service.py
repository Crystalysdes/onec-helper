import json
import base64
from typing import List, Optional
import anthropic
from loguru import logger

from backend.config import settings


class AIService:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.CLAUDE_MODEL

    async def parse_invoice(self, ocr_text: str) -> List[dict]:
        """Parse invoice text and extract product list using Claude."""
        if not ocr_text.strip():
            return []

        prompt = f"""Ты — система обработки накладных для розничного магазина.

Тебе дан текст, извлечённый из накладной с помощью OCR.
Твоя задача — извлечь список товаров и вернуть их в формате JSON.

Текст накладной:
{ocr_text}

Верни ТОЛЬКО валидный JSON массив объектов без каких-либо пояснений.
Каждый объект должен содержать следующие поля (если они есть в тексте):
- name: string (название товара, обязательно)
- article: string (артикул, если есть)
- barcode: string (штрих-код, если есть)
- quantity: number (количество, по умолчанию 1)
- unit: string (единица измерения: шт, кг, л, упак и т.д., по умолчанию "шт")
- price: number (цена за единицу без НДС, если есть)
- purchase_price: number (цена закупки/себестоимость, если есть)
- category: string (категория товара, если можно определить)

Пример ответа:
[
  {{"name": "Молоко 3.2% 1л", "article": "MLK001", "quantity": 10, "unit": "шт", "price": 89.90, "purchase_price": 65.00, "category": "Молочные продукты"}},
  {{"name": "Хлеб белый", "quantity": 5, "unit": "шт", "price": 45.00}}
]

Если товаров не найдено, верни пустой массив: []"""

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"AI invoice parse JSON error: {e}")
            return []
        except Exception as e:
            logger.error(f"AI invoice parse error: {e}")
            return []

    async def recognize_product_from_image(
        self, ocr_text: str, image_bytes: Optional[bytes] = None
    ) -> dict:
        """Recognize product details from image and/or OCR text."""
        messages = []

        if image_bytes:
            base64_image = base64.standard_b64encode(image_bytes).decode("utf-8")
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64_image,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"""Ты — система распознавания товаров для розничного магазина.

Проанализируй изображение товара и извлечённый OCR текст:
{ocr_text if ocr_text else 'OCR текст недоступен'}

Верни ТОЛЬКО валидный JSON объект с полями товара:
- name: string (название товара, обязательно)
- barcode: string (штрих-код, если виден)
- article: string (артикул, если виден)
- category: string (категория товара)
- price: number (цена, если видна)
- description: string (краткое описание)

Верни только JSON без пояснений.""",
                    },
                ],
            })
        else:
            messages.append({
                "role": "user",
                "content": f"""Распознай товар из следующего OCR текста:
{ocr_text}

Верни ТОЛЬКО валидный JSON объект с полями:
- name, barcode, article, category, price, description""",
            })

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=messages,
            )
            content = response.content[0].text.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        except Exception as e:
            logger.error(f"AI product recognition error: {e}")
            return {"name": "Неизвестный товар", "description": ocr_text[:200]}

    async def chat_assistant(self, message: str, context: dict = None) -> str:
        """General AI assistant for product management queries."""
        system_prompt = """Ты — AI-ассистент для управления товарами розничного магазина.
Ты помогаешь владельцам магазинов:
- Добавлять и редактировать товары
- Анализировать остатки и ценообразование
- Работать с накладными и инвентаризацией
- Интегрироваться с системой 1С

Отвечай кратко и по делу на русском языке.
Если пользователь отправляет данные о товаре, структурируй их в JSON формат."""

        context_str = ""
        if context:
            context_str = f"\nКонтекст магазина:\n{json.dumps(context, ensure_ascii=False, indent=2)}"

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": message + context_str}],
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"AI chat error: {e}")
            return "Извините, произошла ошибка. Попробуйте позже."

    async def extract_product_from_text(self, text: str) -> dict:
        """Extract product info from free-form text message."""
        prompt = f"""Ты — система разбора описания товара для розничного магазина.
Пользователь вводит текст в произвольном формате. Разбери его и верни JSON.

Текст пользователя:
"{text}"

Правила разбора:
- "цена NNN" или "NNN р/руб/₽" → price
- "закуп NNN" или "себест NNN" → purchase_price  
- "NNNшт/кг/л/упак/пара" или "N штук/килограмм" → quantity + unit
- числовой баркод (8-13 цифр) или "штрих-код NNNNN" → barcode
- "арт NNN" или "артикул NNN" → article
- название бренда/производителя (Простоквашино, Nestle и т.д.) → добавь в name
- категорию можно определить по смыслу (молочные, выпечка, хозтовары и т.д.)
- слова "штрих код", "qr", "qr код" без числа — игнорируй

Примеры:
"молоко 3.2% 1л Простоквашино цена 89 закуп 65" →
{{"name":"Молоко 3.2% 1л Простоквашино","price":89,"purchase_price":65,"unit":"л","quantity":1,"category":"Молочные продукты"}}

"салфетки большие цена 120 8шт штрих код" →
{{"name":"Салфетки большие","price":120,"quantity":8,"unit":"шт","category":"Хозтовары"}}

"хлеб белый нарезной 450г 4601234567890 45р категория выпечка" →
{{"name":"Хлеб белый нарезной 450г","price":45,"barcode":"4601234567890","category":"Выпечка","unit":"шт","quantity":1}}

Верни ТОЛЬКО JSON объект с полями (null если не найдено):
name, price, purchase_price, barcode, article, category, quantity, unit, description

Верни только JSON без пояснений."""

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        except Exception as e:
            logger.error(f"AI text extraction error: {e}")
            return {"name": text[:100]}
