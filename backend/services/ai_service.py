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
                timeout=90.0,
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
                timeout=90.0,
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

    async def _call_invoice(self, messages: list, max_tokens: int = 8192) -> str:
        """Call dedicated Claude Opus 4 model for invoice parsing."""
        model = settings.OPENROUTER_INVOICE_MODEL if self._mode == "openai" else settings.CLAUDE_MODEL
        if self._mode == "openai":
            r = await self._client.chat.completions.create(
                model=model, max_tokens=max_tokens, messages=messages
            )
            return r.choices[0].message.content.strip()
        r = await self._client.messages.create(
            model=model, max_tokens=max_tokens, messages=messages
        )
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

    async def _extract_invoice_header(self, first_image_bytes: bytes) -> dict:
        """Pass 1: Extract column structure and document info from first invoice photo."""
        b64 = base64.standard_b64encode(first_image_bytes).decode()
        prompt = """Ты анализируешь первое фото товарной накладной. Твоя задача — точно определить структуру таблицы.

=== ШАГ 1: НАЙДИ ШАПКУ ТАБЛИЦЫ ===
Шапка может быть:
- Одна строка заголовков
- ДВЕ строки заголовков (объедини их: "Цена" + "без НДС" → "Цена без НДС")
- Вообще отсутствовать (старый/неформальный документ)

=== ШАГ 2: ОПРЕДЕЛИ КАЖДУЮ КОЛОНКУ ===
Запиши все колонки слева направо в массив "columns".
Затем укажи индексы (0-based) для каждого поля:

col_name (ОБЯЗАТЕЛЬНО):
  Варианты: "Наименование", "Наименование товара", "Товар", "Товар/Услуга", "Описание", "Номенклатура"

col_article:
  Варианты: "Артикул", "Код", "Арт.", "Арт", "Код товара", "Номер"
  НЕ путать с колонкой "№" (порядковый номер строки) — это НЕ артикул!

col_unit:
  Варианты: "Ед.", "Ед.изм.", "Единица", "Ед. изм.", "Ед.изм", "Упак."

col_qty:
  Варианты: "Кол-во", "Количество", "Кол.", "Кол-во (шт)", "Кол. по докум."

col_purchase_price (КРИТИЧНО — читай внимательно):
  Это ЦЕНА ЗА ЕДИНИЦУ ТОВАРА, НЕ итоговая сумма строки!
  Варианты: "Цена", "Цена без НДС", "Цена с НДС", "Цена руб.", "Закупочная цена", "Цена поставщика"
  НЕЛЬЗЯ указывать: "Сумма", "Стоимость", "Итого", "Сумма без НДС", "Сумма с НДС" — это итог строки (кол-во × цена)!
  Правило: если в документе несколько колонок цен — выбирай ПЕРВУЮ (обычно "Цена без НДС")

col_price:
  Только если явно есть колонка розничной/отпускной цены: "Розничная", "Цена продажи", "Отпускная цена"
  В большинстве накладных = null

col_barcode:
  Варианты: "Штрих-код", "ШК", "Баркод", "EAN", "Штрих код"

=== ШАГ 3: РЕКВИЗИТЫ ДОКУМЕНТА ===
supplier: полное название организации-поставщика
doc_number: номер документа
doc_date: дата в формате ДД.ММ.ГГГГ
doc_type: ТОРГ-12 / УПД / Счёт-фактура / Накладная / Товарный чек / УПД(СЧФ)

=== ЕСЛИ ШАПКИ НЕТ ===
Посмотри на первую строку данных и определи формат по количеству колонок и типу значений.
Верни columns: [] и проставь индексы null, кроме col_name: 0.

Верни ТОЛЬКО JSON без пояснений:
{
  "columns": [],
  "col_name": 0,
  "col_article": null,
  "col_unit": null,
  "col_qty": null,
  "col_purchase_price": null,
  "col_price": null,
  "col_barcode": null,
  "supplier": null,
  "doc_number": null,
  "doc_date": null,
  "doc_type": null
}"""

        content = [self._img_block(b64), {"type": "text", "text": prompt}]
        messages = [{"role": "user", "content": content}]
        try:
            result = await self._call_invoice(messages, max_tokens=1024)
            header = json.loads(_strip_json(result))
            logger.info(f"Invoice header extracted: cols={header.get('columns')}, "
                        f"supplier={header.get('supplier')}, doc={header.get('doc_number')}")
            return header
        except Exception as e:
            logger.warning(f"Header extraction failed ({e}), proceeding without column context")
            return {"columns": [], "col_name": 0}

    def _build_column_context(self, header: dict) -> str:
        """Build human-readable column mapping for the parsing prompt."""
        columns = header.get("columns") or []
        if not columns:
            return (
                "Шапка таблицы не обнаружена — определяй поля каждой строки самостоятельно по контексту.\n"
                "Типичный порядок колонок в накладных: № | Наименование | Ед. | Кол-во | Цена | Сумма\n"
                "ВАЖНО: «Цена» — цена за единицу товара; «Сумма» — итог строки (кол-во × цена), НЕ является ценой за единицу!"
            )

        field_map = [
            ("col_name",           "name            (название товара, ОБЯЗАТЕЛЬНО)"),
            ("col_article",        "article          (артикул/код)"),
            ("col_unit",           "unit             (единица измерения)"),
            ("col_qty",            "quantity         (количество)"),
            ("col_purchase_price", "purchase_price   (цена за единицу — НЕ итог строки!)"),
            ("col_price",          "price            (розничная цена продажи)"),
            ("col_barcode",        "barcode          (штрих-код EAN)"),
        ]
        cols_str = "  ".join(f"{i}:{c}" for i, c in enumerate(columns))
        lines = [f"Колонки (слева→право): {cols_str}", "Маппинг:"]
        for key, desc in field_map:
            idx = header.get(key)
            if idx is not None and isinstance(idx, int) and idx < len(columns):
                lines.append(f"  [{idx}] «{columns[idx]}» → {desc}")
        used = {header.get(k) for k, _ in field_map}
        ignored = [i for i in range(len(columns)) if i not in used]
        if ignored:
            ign_names = ", ".join(f"{i}:«{columns[i]}»" for i in ignored)
            lines.append(f"  Игнорировать: {ign_names}")
        # Always add the price-vs-total warning
        lines.append(
            "\nВАЖНО: «Цена»/«Цена без НДС» = цена за ЕДИНИЦУ товара (purchase_price).\n"
            "«Сумма»/«Стоимость»/«Итого по строке» = кол-во × цена — это НЕ цена за единицу, игнорируй!"
        )
        return "\n".join(lines)

    async def parse_invoice_from_images(self, images_bytes: List[bytes]) -> List[dict]:
        """
        Smart 2-pass invoice parsing using Claude Opus 4.

        Pass 1 (first photo only): extract column header structure — which column
                                   is the name, quantity, price, etc.
        Pass 2 (all photos):       parse every product row using the column mapping
                                   so data is correctly mapped even on photos where
                                   the column header row is no longer visible.
        """
        if not images_bytes:
            return []

        multi = len(images_bytes) > 1

        # ── Pass 1: extract header from first photo ──────────────────────
        logger.info(f"Invoice Pass 1: extracting header from first of {len(images_bytes)} photo(s)")
        header = await self._extract_invoice_header(images_bytes[0])
        col_context = self._build_column_context(header)

        # ── Build meta hints ─────────────────────────────────────────────
        meta = ""
        if header.get("supplier"):
            meta += f"Поставщик: {header['supplier']}. "
        if header.get("doc_type"):
            meta += f"Тип: {header['doc_type']}. "
        if header.get("doc_number"):
            meta += f"№{header['doc_number']}. "
        if header.get("doc_date"):
            meta += f"Дата: {header['doc_date']}."

        # ── Pass 2: parse all photos with column context ──────────────────
        logger.info("Invoice Pass 2: parsing all photos with column context")

        multi_note = (
            "Накладная СФОТОГРАФИРОВАНА СВЕРХУ ВНИЗ несколькими фото.\n"
            "Шапка таблицы (заголовки колонок) ВИДНА ТОЛЬКО НА ПЕРВОМ ФОТО.\n"
            "На остальных фото шапки нет — колонки те же, используй маппинг ниже."
        ) if multi else "На фото — товарная накладная, счёт-фактура или товарный чек."

        prompt = f"""Ты — профессиональная система распознавания товарных накладных. {meta}
{multi_note}

СТРУКТУРА ТАБЛИЦЫ (применяй к КАЖДОЙ строке на КАЖДОМ фото):
{col_context}

ЗАДАЧА: извлечь ПОЛНЫЙ список товарных строк со всех фото.

ПРАВИЛА:
1. {'Каждый товар встречается только на одном фото — не дублируй.' if multi else 'Каждую строку товара включи ровно один раз.'}
2. Применяй маппинг колонок к каждой строке, даже где шапка не видна
3. ИГНОРИРУЙ строки: «Итого», «НДС», «Скидка», «Всего», суммарные строки, реквизиты, подписи, пустые строки
4. barcode — только цифры EAN (8–13 знаков), иначе null
5. Нормализуй названия: правильный регистр, убери лишние коды и мусорные символы из названия
6. quantity — дробное число для кг/л, целое для шт; по умолчанию 1
7. unit — шт/кг/г/л/мл/упак/пара/м/рулон; по умолчанию «шт»
8. Если в документе только одна колонка цен → записывай в purchase_price

Верни ТОЛЬКО JSON массив без текста до и после:
[{{"name":"Название товара","article":null,"barcode":null,"quantity":1,"unit":"шт","purchase_price":100.50,"price":null,"category":null}}]

Если товаров нет — верни []"""

        content = []
        for img_bytes in images_bytes:
            b64 = base64.standard_b64encode(img_bytes).decode()
            content.append(self._img_block(b64))
        content.append({"type": "text", "text": prompt})

        messages = [{"role": "user", "content": content}]
        result = None
        try:
            result = await self._call_invoice(messages, max_tokens=8192)
            products = json.loads(_strip_json(result))
            logger.info(f"Invoice parsed: {len(products)} products extracted")
            return products
        except json.JSONDecodeError as e:
            logger.error(f"Invoice JSON parse error: {e}. Preview: {result[:400] if result else 'empty'}")
            return []
        except Exception as e:
            logger.error(f"Invoice parse error: {e}")
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
