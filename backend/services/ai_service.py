import json
import base64
from typing import List, Optional
from loguru import logger

from backend.config import settings


def _strip_json(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    return content.strip()


class AIService:
    def __init__(self):
        if settings.OPENROUTER_API_KEY:
            from openai import AsyncOpenAI
            self._mode = "openai"
            self._client = AsyncOpenAI(
                api_key=settings.OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
                default_headers={"HTTP-Referer": "https://net1c.ru", "X-Title": "1C Helper"},
                timeout=40.0,
            )
            self._model = settings.OPENROUTER_MODEL
            self._fast_model = settings.OPENROUTER_FAST_MODEL
            self._vision_model = getattr(settings, 'OPENROUTER_VISION_MODEL', settings.OPENROUTER_FAST_MODEL)
            logger.info(f"AIService: OpenRouter mode, model={self._model}, fast={self._fast_model}, vision={self._vision_model}")
        else:
            import anthropic
            self._mode = "anthropic"
            self._client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY,
                timeout=40.0,
            )
            self._fast_model = settings.CLAUDE_MODEL
            self._vision_model = settings.CLAUDE_MODEL
            self._model = settings.CLAUDE_MODEL
            logger.info(f"AIService: Anthropic direct mode, model={self._model}")

    def _img_block(self, b64: str) -> dict:
        if self._mode == "openai":
            return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}

    async def _call(self, messages: list, system: str = None, max_tokens: int = 1024, fast: bool = False) -> str:
        model = self._fast_model if fast else self._model
        if self._mode == "openai":
            msgs = ([{"role": "system", "content": system}] if system else []) + messages
            r = await self._client.chat.completions.create(
                model=model, max_tokens=max_tokens, messages=msgs
            )
            return r.choices[0].message.content.strip()
        kwargs = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if system:
            kwargs["system"] = system
        r = await self._client.messages.create(**kwargs)
        return r.content[0].text.strip()

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
            content = await self._call([{"role": "user", "content": prompt}], max_tokens=4096)
            return json.loads(_strip_json(content))
        except json.JSONDecodeError as e:
            logger.error(f"AI invoice parse JSON error: {e}")
            return []
        except Exception as e:
            logger.error(f"AI invoice parse error: {e}")
            return []

    async def parse_invoice_from_image(self, image_bytes: bytes) -> List[dict]:
        """Parse invoice by sending image directly to Claude vision (when OCR is unavailable)."""
        base64_image = base64.standard_b64encode(image_bytes).decode("utf-8")
        prompt = """Ты — система обработки накладных для розничного магазина.
На изображении — накладная, товарный чек или счёт-фактура.
Извлеки СПИСОК ТОВАРОВ и верни ТОЛЬКО валидный JSON массив объектов.

Поля каждого объекта:
- name: string — полное нормализованное название (обязательно, правильный регистр)
- article: string|null — артикул/код товара
- barcode: string|null — штрих-код EAN/UPC (только цифры 8-13 знаков)
- quantity: number — количество (дробное если кг/л), по умолчанию 1
- unit: string — шт/кг/л/упак/пара/м/рулон, по умолчанию "шт"
- price: number|null — цена продажи за единицу
- purchase_price: number|null — закупочная цена / себестоимость
- category: string|null — Молочные продукты / Выпечка / Хозтовары / Бакалея и т.д.

Правила:
- Нормализуй названия: правильный регистр, убери лишние символы и коды
- Если одна колонка цен — это purchase_price
- Игнорируй строки: итого, НДС, сумма, заголовки колонок, реквизиты поставщика

Верни только JSON массив без пояснений. Если товаров нет — []"""

        messages = [{
            "role": "user",
            "content": [
                self._img_block(base64_image),
                {"type": "text", "text": prompt},
            ],
        }]
        try:
            content = await self._call(messages, max_tokens=4096)
            return json.loads(_strip_json(content))
        except json.JSONDecodeError as e:
            logger.error(f"AI invoice image parse JSON error: {e}")
            return []
        except Exception as e:
            logger.error(f"AI invoice image parse error: {e}")
            return []

    async def recognize_product_from_image(
        self, ocr_text: str, image_bytes: Optional[bytes] = None
    ) -> dict:
        """Recognize product details from image using fast AI vision."""
        if not image_bytes:
            return {"name": ocr_text[:100] if ocr_text else "Неизвестный товар"}

        base64_image = base64.standard_b64encode(image_bytes).decode("utf-8")
        messages = [{
            "role": "user",
            "content": [
                self._img_block(base64_image),
                {
                    "type": "text",
                    "text": """Определи товар на фото. Верни ТОЛЬКО JSON без пояснений:
{"name":"[Вид] [Бренд] [объём/вес]","barcode":null,"article":null,"category":null,"price":null,"description":null}

Правила:
- name: нормализованное название (первое слово заглавное, бренды заглавные), например "Молоко Простоквашино 1л"
- barcode: цифры штрихкода если виден (8-13 цифр), иначе null
- category: Напитки/Молочные/Выпечка/Хозтовары/Бакалея/Снеки/Косметика/Алкоголь/Табак или null
- price: число если видна цена, иначе null""",
                },
            ],
        }]

        try:
            content = await self._call(messages, max_tokens=200, fast=True)
            return json.loads(_strip_json(content))
        except Exception as e:
            logger.error(f"AI product recognition error: {e}")
            return {"name": "Неизвестный товар"}

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
            return await self._call(
                [{"role": "user", "content": message + context_str}],
                system=system_prompt,
                max_tokens=2048,
            )
        except Exception as e:
            logger.error(f"AI chat error: {e}")
            return "Извините, произошла ошибка. Попробуйте позже."

    async def extract_product_from_text(self, text: str) -> dict:
        """Extract and normalize product info from free-form text message."""
        prompt = f"""Нормализуй товар для розничного магазина. Текст: "{text}"

Правила:
- quantity и unit — СНАЧАЛА ищи явно написанное количество с единицей (10шт, 5кг, 3упак, 2л).
  Если найдено — используй ТОЧНО ЭТО, не меняй unit на основе типа товара.
  Примеры: "сок 10шт"→quantity=10,unit="шт"; "вода 5л"→quantity=5,unit="л"; "чай 3упак"→quantity=3,unit="упак"
  Если не найдено — quantity=1, unit="шт".
  Словарь: шт/штук/штуки→"шт"; кг/кило/килограмм→"кг"; л/лит/литр→"л"; пак/упак/пачка/упаковка→"упак"; м/метр→"м"
- name: [Вид] [Бренд] ([вкус/состав]) [объём]. Регистр: первое слово заглавное, бренды каждое слово заглавное.
  Разворачивай сокращения: "ябл"→"Яблоко", "вишн"→"Вишня", "апел"→"Апельсин", "клубн"→"Клубника", "малин"→"Малина".
  Восстанавливай полное название бренда: "сады придон"→"Сады Придонья", "добрый"→"Добрый", "риобраво"→"Rio Bravo".
  Вкусы/состав/варианты — в скобках после бренда.
  Убери из name: цену, руб/₽/р, закуп, явно написанное количество (уже в quantity).
  Объём/вес который ВХОДИТ В НАЗВАНИЕ ТОВАРА (на упаковке) — оставь в name.
  Примеры:
  "сок ябл вишня 10шт сады придон"→name="Сок Сады Придонья (Яблоко Вишня)", qty=10, unit="шт"
  "крым лимонад 2 литра пак 10шт"→name="Лимонад Крым 2л", qty=10, unit="шт"
  "жижа вейп сладкое яблоко 10шт"→name="Жидкость для вейпа (Сладкое яблоко)", qty=10, unit="шт"
  "молоко простоквашино 1л 5шт"→name="Молоко Простоквашино 1л", qty=5, unit="шт"
  "чипсы лейс сметана лук 6упак"→name="Чипсы Lay's (Сметана и лук)", qty=6, unit="упак"
- price: число после цена/₽/р/руб
- purchase_price: число после закуп/себест/приход
- barcode: только цифры 8-13 знаков
- article: после арт/артикул
- category: Напитки/Молочные продукты/Выпечка/Хозтовары/Бакалея/Снеки/Мясо и птица/Кондитерские/Алкоголь/Косметика/Табак

Верни ТОЛЬКО JSON без пояснений:
{{"name":"...","price":null,"purchase_price":null,"barcode":null,"article":null,"category":null,"quantity":1,"unit":"шт","description":null}}"""

        try:
            content = await self._call([{"role": "user", "content": prompt}], max_tokens=200, fast=True)
            return json.loads(_strip_json(content))
        except Exception as e:
            logger.error(f"AI text extraction error: {e}")
            return {"name": text[:100]}
