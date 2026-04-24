import json
import os
import time
import base64
from typing import List, Optional
from loguru import logger

from backend.config import settings


# Anthropic beta header required to raise max_tokens above 8192 for Claude 3.5 Sonnet.
# Safe to send on all requests — ignored by models that don't support it.
_ANTHROPIC_EXTENDED_OUTPUT_HEADER = {"anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"}


def _strip_json(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    return content.strip()


def _parse_json_resilient(raw: str, tag: str = "") -> list:
    """Parse a JSON array from Claude's output, tolerating malformed strings.

    Claude sometimes returns JSON with unescaped double quotes inside product names
    (e.g. `"name": "Конфеты "Раф-Раф""`). A strict json.loads rejects this and we
    lose the ENTIRE invoice. This function tries progressively lenient parsers.

    Returns the parsed list, or raises json.JSONDecodeError on total failure
    (after logging extensive diagnostics).
    """
    import re
    stripped = _strip_json(raw)

    # Attempt 1: standard JSON
    try:
        data = json.loads(stripped)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError as e:
        err_pos = e.pos if hasattr(e, "pos") else 0
        ctx_start = max(0, err_pos - 80)
        ctx_end = min(len(stripped), err_pos + 80)
        logger.warning(
            f"JSON[{tag}] strict parse failed at char {err_pos}/{len(stripped)}: {e.msg}. "
            f"Context: ...{stripped[ctx_start:err_pos]!r}⟦HERE⟧{stripped[err_pos:ctx_end]!r}..."
        )

    # Attempt 2: object-by-object extraction via regex (ignore outer brackets)
    # Matches `{ ... }` blocks non-greedily, skipping over malformed ones.
    results = []
    # Find all top-level objects inside the array. Balanced-brace scan.
    s = stripped
    # Strip wrapping [ ] if present
    if s.startswith("["):
        s = s[1:]
    if s.endswith("]"):
        s = s[:-1]

    depth = 0
    start = None
    i = 0
    n = len(s)
    in_str = False
    esc = False
    while i < n:
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                # Heuristic: if this quote is followed (ignoring ws) by ':' it was a key-end,
                # if followed by ',' or '}' it was a value-end. Otherwise likely unescaped.
                j = i + 1
                while j < n and s[j] in " \t\n\r":
                    j += 1
                if j < n and s[j] in ':,}]':
                    in_str = False
                # else: treat as literal inside the string (don't close it)
        else:
            if ch == '"':
                in_str = True
            elif ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start is not None:
                    obj_str = s[start:i + 1]
                    try:
                        obj = json.loads(obj_str)
                        results.append(obj)
                    except json.JSONDecodeError:
                        # try replacing internal unescaped quotes with ' — last resort
                        fixed = re.sub(
                            r'("(?:name|article|category|unit|description)"\s*:\s*")'
                            r'((?:[^"\\]|\\.)*?)'
                            r'(")([^,}\]]*?)(?=[,}])',
                            lambda m: (
                                m.group(1)
                                + (m.group(2) + m.group(3) + m.group(4)).replace('"', "'")
                                + '"'
                            ),
                            obj_str,
                        )
                        try:
                            obj = json.loads(fixed)
                            results.append(obj)
                        except json.JSONDecodeError:
                            logger.debug(f"JSON[{tag}] dropped malformed object: {obj_str[:160]!r}")
                    start = None
        i += 1

    if results:
        logger.info(
            f"JSON[{tag}] recovered {len(results)} objects from malformed response "
            f"(length={len(stripped)})"
        )
        return results

    # Total failure
    logger.error(
        f"JSON[{tag}] ALL recovery attempts failed. "
        f"First 400 chars: {stripped[:400]!r}. Last 200: {stripped[-200:]!r}"
    )
    raise json.JSONDecodeError("Could not recover any valid objects", stripped, 0)


_PROXY_FILE = "/app/data/proxy.txt"
_MAX_IMAGE_BYTES = 3_500_000  # ~3.5 MB raw keeps base64 under Anthropic's 5 MB limit


def _compress_image(image_bytes: bytes, max_bytes: int = _MAX_IMAGE_BYTES) -> bytes:
    """Resize/compress image so raw size stays under max_bytes."""
    if len(image_bytes) <= max_bytes:
        return image_bytes
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        for quality in (85, 70, 55, 40, 25):
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=quality)
            if buf.tell() <= max_bytes:
                logger.debug(f"Image compressed: {len(image_bytes)//1024}KB → {buf.tell()//1024}KB (q={quality})")
                return buf.getvalue()
        # Still too large — scale down
        scale = (max_bytes / len(image_bytes)) ** 0.5
        new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
        img = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=70)
        logger.debug(f"Image resized to {new_size}: {buf.tell()//1024}KB")
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"Image compression failed ({e}), using original")
        return image_bytes


_CATEGORIES = """\
ПРОДУКТЫ ПИТАНИЯ:
  Молочные продукты       — молоко, кефир, творог, сыр, масло, йогурт, сметана, ряженка
  Мясо и птица            — говядина, свинина, курица, колбаса, сосиски, ветчина, деликатесы
  Рыба и морепродукты     — рыба, икра, креветки, кальмары, морепродукты
  Хлеб и выпечка          — хлеб, батон, булка, пирог, лаваш, тесто
  Напитки                 — вода, сок, чай, кофе, лимонад, газировка, энергетик
  Алкоголь                — пиво, вино, водка, коньяк, шампанское, ликёр
  Бакалея                 — крупа, макароны, мука, сахар, соль, рис, гречка
  Кондитерские изделия    — конфеты, шоколад, торт, печенье, вафли, зефир, мармелад
  Снеки                   — чипсы, сухарики, орехи, семечки, попкорн
  Консервы                — тушёнка, рыбные консервы, овощные консервы, варенье
  Овощи и фрукты          — овощи, фрукты, ягоды, зелень
  Замороженные продукты   — пельмени, вареники, мороженое, замороженные овощи
  Масла и соусы           — подсолнечное масло, оливковое, кетчуп, майонез, соус
  Детское питание         — смеси, пюре, каши для детей

ЭЛЕКТРОНИКА И АКСЕССУАРЫ:
  Кабели и переходники    — USB кабель, Type-C, Lightning, HDMI, переходник, удлинитель, шнур
  Зарядные устройства     — зарядка, адаптер, блок питания, сетевой адаптер, беспроводная зарядка
  Аксессуары для телефонов — чехол, защитное стекло, плёнка, держатель, попсокет
  Наушники и аудио        — наушники, гарнитура, колонка, TWS, bluetooth гарнитура
  Компьютерная техника    — ноутбук, планшет, клавиатура, мышь, монитор, USB хаб, флешка, SSD
  Смартфоны и телефоны    — смартфон, телефон, айфон
  Электроника             — телевизор, камера, умные часы, фитнес-браслет, роутер, прочая электроника

ТОВАРЫ ДЛЯ ДОМА:
  Бытовая техника         — пылесос, холодильник, стиральная машина, микроволновка, утюг, фен
  Бытовая химия           — стиральный порошок, средство для мытья, отбеливатель, освежитель
  Посуда и кухня          — тарелки, кастрюли, сковородки, столовые приборы, контейнеры
  Текстиль                — полотенца, постельное бельё, шторы, подушки, одеяла
  Инструменты             — молоток, дрель, отвёртка, ключи, строительные инструменты
  Товары для дома         — светильник, батарейки, лампочки, замок, крепёж, прочее для дома

ЛИЧНАЯ ГИГИЕНА И КРАСОТА:
  Средства гигиены        — мыло, шампунь, зубная паста, щётка, дезодорант, гель для душа
  Косметика и парфюмерия  — крем, помада, тушь, тени, духи, парфюм, лак для ногтей

ПРОЧИЕ КАТЕГОРИИ:
  Одежда и обувь          — одежда, обувь, носки, перчатки, шапка
  Игрушки                 — игрушки, конструктор, кукла, машинка, настольные игры
  Спортивные товары       — спортинвентарь, тренажёр, велосипед, ролики
  Канцелярия              — ручка, тетрадь, бумага, скрепки, папка, маркер
  Автотовары              — масло моторное, автохимия, аксессуары для авто
  Зоотовары               — корм для животных, наполнитель, ошейник, поводок
  Медицинские товары      — лекарства, витамины, маска, перчатки медицинские
  Стройматериалы          — краска, плитка, цемент, обои, ламинат
  Табак и вейп            — сигареты, вейп, жидкость для вейпа, стики
  Прочее                  — всё что не подходит ни под одну категорию выше
"""

_CATEGORY_RULE = (
    "category — выбери САМУЮ КОНКРЕТНУЮ подходящую категорию из списка выше. "
    "Ориентируйся на ключевые слова в названии товара. "
    "'Прочее' используй ТОЛЬКО если товар действительно не подходит ни под одну другую категорию. "
    "Возвращай только название категории (например: Кабели и переходники), без пояснений."
)


def _get_proxy_list() -> List[Optional[str]]:
    """Return list of proxy URLs. File overrides env. Returns [None] if none configured."""
    try:
        if os.path.exists(_PROXY_FILE):
            raw = open(_PROXY_FILE).read().strip()
            if raw:
                try:
                    data = json.loads(raw)
                    if isinstance(data, list):
                        proxies = [p.strip() for p in data if p and str(p).strip()]
                        return proxies if proxies else [None]
                    elif isinstance(data, str) and data.strip():
                        return [data.strip()]
                except (json.JSONDecodeError, TypeError):
                    return [raw]  # old plain-text format
    except Exception:
        pass
    env_proxy = (settings.ANTHROPIC_PROXY_URL or "").strip() or None
    return [env_proxy] if env_proxy else [None]


def _is_proxy_error(exc) -> bool:
    """True if the exception looks like a proxy / connectivity failure."""
    try:
        import httpx
        if isinstance(exc, (httpx.ConnectError, httpx.ProxyError,
                            httpx.ConnectTimeout, httpx.RemoteProtocolError)):
            return True
    except ImportError:
        pass
    msg = str(exc).lower()
    return any(k in msg for k in ("proxy", "connect", "tunnel", "socks", "eof", "connection refused"))


class AIService:
    def __init__(self):
        import httpx
        proxies = _get_proxy_list()  # e.g. ["socks5://...", "http://..."] or [None]
        self._active_idx = 0

        if not settings.OPENROUTER_API_KEY and not settings.ANTHROPIC_API_KEY:
            raise ValueError(
                "AI не настроен: задайте OPENROUTER_API_KEY (рекомендуется) "
                "или ANTHROPIC_API_KEY в файле /app/.env на сервере и перезапустите контейнер."
            )

        if settings.OPENROUTER_API_KEY:
            from openai import AsyncOpenAI
            self._mode = "openai"
            self._model = settings.OPENROUTER_MODEL
            self._fast_model = settings.OPENROUTER_FAST_MODEL
            self._vision_model = getattr(settings, 'OPENROUTER_VISION_MODEL', settings.OPENROUTER_FAST_MODEL)
            self._clients = []
            for p in proxies:
                kw = {
                    "api_key": settings.OPENROUTER_API_KEY,
                    "base_url": "https://openrouter.ai/api/v1",
                    "default_headers": {"HTTP-Referer": "https://net1c.ru", "X-Title": "1C Helper"},
                    "timeout": 90.0,
                }
                if p:
                    kw["http_client"] = httpx.AsyncClient(proxy=p, timeout=90.0)
                self._clients.append(AsyncOpenAI(**kw))
            proxy_info = f" proxies={proxies}" if proxies != [None] else ""
            logger.info(f"AIService: OpenRouter mode, model={self._model}{proxy_info}")
        else:
            import anthropic
            self._mode = "anthropic"
            self._fast_model = settings.CLAUDE_MODEL
            self._vision_model = settings.CLAUDE_MODEL
            self._model = settings.CLAUDE_MODEL
            self._clients = []
            api_key = settings.ANTHROPIC_API_KEY or ""
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY не задан в .env. "
                    "Добавьте OPENROUTER_API_KEY или ANTHROPIC_API_KEY и перезапустите контейнер."
                )
            for p in proxies:
                kw = {"api_key": api_key, "timeout": 90.0}
                if p:
                    kw["http_client"] = httpx.AsyncClient(proxy=p, timeout=90.0)
                self._clients.append(anthropic.AsyncAnthropic(**kw))
            proxy_info = f" proxies={proxies}" if proxies != [None] else ""
            logger.info(f"AIService: Anthropic direct mode, model={self._model}{proxy_info}")

        # keep self._client as alias for the current active client
        self._client = self._clients[0]

        # ── Dedicated Anthropic clients for INVOICE PARSING ──────────────────
        # Per product decision: invoice scanning MUST go directly to Anthropic
        # (never via OpenRouter), using the same proxy list. All other AI calls
        # can stay on OpenRouter if it is configured.
        self._invoice_clients = []
        self._invoice_model = settings.ANTHROPIC_INVOICE_MODEL
        self._invoice_active_idx = 0
        if settings.ANTHROPIC_API_KEY:
            import anthropic as _anthropic
            for p in proxies:
                kw = {"api_key": settings.ANTHROPIC_API_KEY, "timeout": 90.0}
                if p:
                    kw["http_client"] = httpx.AsyncClient(proxy=p, timeout=90.0)
                self._invoice_clients.append(_anthropic.AsyncAnthropic(**kw))
            logger.info(
                f"AIService: invoice pipeline → Anthropic direct, model={self._invoice_model}"
                f"{(' proxies=' + str(proxies)) if proxies != [None] else ''}"
            )
        else:
            logger.warning(
                "AIService: ANTHROPIC_API_KEY is not set — invoice parsing will FALL BACK "
                "to the main provider. Set ANTHROPIC_API_KEY in .env for direct-to-Anthropic invoice parsing."
            )

    def _img_block(self, b64: str) -> dict:
        if self._mode == "openai":
            return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}

    def _invoice_img_block(self, b64: str) -> dict:
        """Invoice pipeline always goes to Anthropic, so always return Anthropic-format image block."""
        return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}

    async def _do_call_openai(self, client, model: str, max_tokens: int, msgs: list) -> str:
        r = await client.chat.completions.create(model=model, max_tokens=max_tokens, messages=msgs)
        return r.choices[0].message.content.strip()

    async def _do_call_anthropic(
        self, client, model: str, max_tokens: int, messages: list,
        system: str = None, tag: str = "generic",
    ) -> str:
        """Call Anthropic and log latency + stop_reason + token usage.

        Logs a WARNING if stop_reason == "max_tokens" — that means the JSON
        was truncated and the caller will likely hit a JSONDecodeError.
        """
        kw = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if system:
            kw["system"] = system
        # Enable extended output (up to 16384 tokens for Claude 3.5 Sonnet)
        extra = {"extra_headers": _ANTHROPIC_EXTENDED_OUTPUT_HEADER}
        t0 = time.perf_counter()
        r = await client.messages.create(**kw, **extra)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        stop_reason = getattr(r, "stop_reason", None)
        usage = getattr(r, "usage", None)
        in_tok = getattr(usage, "input_tokens", None) if usage else None
        out_tok = getattr(usage, "output_tokens", None) if usage else None
        text = r.content[0].text.strip() if r.content else ""

        log_msg = (
            f"Anthropic[{tag}] model={model} elapsed={elapsed_ms}ms "
            f"stop={stop_reason} in_tok={in_tok} out_tok={out_tok}/{max_tokens} "
            f"resp_chars={len(text)}"
        )
        if stop_reason == "max_tokens":
            logger.warning(f"{log_msg}  ⚠️ OUTPUT TRUNCATED — invoice may lose items!")
        else:
            logger.info(log_msg)
        return text

    async def _call(self, messages: list, system: str = None, max_tokens: int = 1024, fast: bool = False) -> str:
        model = self._fast_model if fast else self._model
        last_exc = None
        n = len(self._clients)
        for i in range(n):
            idx = (self._active_idx + i) % n
            client = self._clients[idx]
            try:
                if self._mode == "openai":
                    msgs = ([{"role": "system", "content": system}] if system else []) + messages
                    result = await self._do_call_openai(client, model, max_tokens, msgs)
                else:
                    result = await self._do_call_anthropic(client, model, max_tokens, messages, system, tag="generic")
                if idx != self._active_idx:
                    logger.info(f"AIService: switched to proxy index {idx}")
                    self._active_idx = idx
                    self._client = client
                return result
            except Exception as e:
                if _is_proxy_error(e) and n > 1:
                    logger.warning(f"AIService: proxy[{idx}] failed ({e}), trying next")
                    last_exc = e
                    continue
                raise
        raise last_exc or RuntimeError("All proxies exhausted")

    async def _call_invoice(self, messages: list, max_tokens: int = 8192) -> str:
        """Invoice parsing goes DIRECTLY to Anthropic (never OpenRouter), with proxy failover.

        The messages argument MUST already be in Anthropic format (use
        self._invoice_img_block for image parts). Falls back to the main
        provider only as a last resort if Anthropic is not configured at all.
        """
        # Fallback path: no Anthropic key configured → use the generic _call
        if not self._invoice_clients:
            logger.warning(
                "Invoice parse: no Anthropic clients configured — falling back to main provider"
            )
            return await self._call(messages, max_tokens=max_tokens)

        model = self._invoice_model
        n = len(self._invoice_clients)
        last_exc = None
        for pi in range(n):
            idx = (self._invoice_active_idx + pi) % n
            client = self._invoice_clients[idx]
            try:
                r = await self._do_call_anthropic(client, model, max_tokens, messages, tag="invoice")
                if idx != self._invoice_active_idx:
                    logger.info(f"AIService invoice: switched to proxy index {idx}")
                    self._invoice_active_idx = idx
                return r
            except Exception as e:
                if _is_proxy_error(e) and n > 1:
                    logger.warning(
                        f"AIService invoice: proxy[{idx}] failed ({type(e).__name__}: {str(e)[:120]}), trying next"
                    )
                    last_exc = e
                    continue
                logger.error(f"AIService invoice: Anthropic call failed ({type(e).__name__}: {str(e)[:200]})")
                raise
        raise last_exc or RuntimeError("All Anthropic proxies exhausted for invoice call")

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
- category: string (категория товара, {_CATEGORY_RULE})

Список категорий:
{_CATEGORIES}

Пример ответа:
[
  {{"name": "Молоко 3.2% 1л", "article": "MLK001", "quantity": 10, "unit": "шт", "price": 89.90, "purchase_price": 65.00, "category": "Молочные продукты"}},
  {{"name": "Кабель USB Type-C 1м", "quantity": 5, "unit": "шт", "purchase_price": 150.00, "category": "Кабели и переходники"}}
]

Если товаров не найдено, верни пустой массив: []"""

        try:
            # Route invoice text parsing through the dedicated Anthropic pipeline
            # so the entire invoice flow (text and vision) consistently uses Claude.
            content = await self._call_invoice(
                [{"role": "user", "content": prompt}], max_tokens=4096
            )
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

        content = [self._invoice_img_block(b64), {"type": "text", "text": prompt}]
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

    async def parse_invoice_from_images(self, images_bytes: List[bytes], _compress: bool = True) -> List[dict]:
        """
        Smart 2-pass invoice parsing using Claude Opus 4.

        Pass 1 (first photo only): extract column header structure — which column
                                   is the name, quantity, price, etc.
        Pass 2 (all photos):       parse every product row using the column mapping
                                   so data is correctly mapped even on photos where
                                   the column header row is no longer visible.
        """
        t_total = time.perf_counter()
        if not images_bytes:
            return []

        raw_bytes_total = sum(len(b) for b in images_bytes)
        if _compress:
            t_c = time.perf_counter()
            images_bytes = [_compress_image(b) for b in images_bytes]
            compressed_total = sum(len(b) for b in images_bytes)
            logger.info(
                f"Invoice: {len(images_bytes)} image(s) compressed in "
                f"{int((time.perf_counter() - t_c) * 1000)}ms "
                f"({raw_bytes_total // 1024}KB → {compressed_total // 1024}KB)"
            )

        multi = len(images_bytes) > 1

        # ── Pass 1: extract header from first photo ──────────────────────
        logger.info(f"Invoice Pass 1: extracting header from first of {len(images_bytes)} photo(s)")
        t_p1 = time.perf_counter()
        header = await self._extract_invoice_header(images_bytes[0])
        logger.info(f"Invoice Pass 1 DONE in {int((time.perf_counter() - t_p1) * 1000)}ms, header={list(header.keys()) if header else '[]'}")
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
5. Нормализуй названия: правильный регистр, убери лишние коды и мусорные символы из названия. НЕ включай количество, единицы измерения или фасовку в название (например «Молоко 1л» → name="Молоко", quantity=1, unit="л")
6. quantity — дробное число для кг/л, целое для шт; по умолчанию 1
7. unit — шт/кг/г/л/мл/упак/пара/м/рулон; по умолчанию «шт»
8. Если в документе только одна колонка цен → записывай в purchase_price
9. category — {_CATEGORY_RULE}
   Список категорий:
{_CATEGORIES}

ПРАВИЛА JSON (КРИТИЧНО):
- Все строковые значения в ДВОЙНЫХ кавычках ASCII: "
- Если в названии товара есть кавычки (например, Конфеты «Мишка»), ЗАМЕНИ их на апостроф '
  или экранируй через \\". НИКОГДА не оставляй неэкранированную " внутри строки.
- Правильно: {{"name": "Конфеты 'Мишка' 200г"}}
- Правильно: {{"name": "Конфеты \\"Мишка\\" 200г"}}
- НЕПРАВИЛЬНО: {{"name": "Конфеты "Мишка" 200г"}}  ← сломает парсер, потеряем ВСЕ товары!
- Никаких одинарных кавычек ' вокруг ключей/значений, только "
- Никаких trailing запятых, никаких комментариев // или /* */

Верни ТОЛЬКО JSON массив без текста до и после:
[{{"name":"Название товара","article":null,"barcode":null,"quantity":1,"unit":"шт","purchase_price":100.50,"price":null,"category":"Бакалея"}}]

Если товаров нет — верни []"""

        content = []
        for img_bytes in images_bytes:
            b64 = base64.standard_b64encode(img_bytes).decode()
            content.append(self._invoice_img_block(b64))
        content.append({"type": "text", "text": prompt})

        messages = [{"role": "user", "content": content}]
        result = None
        t_p2 = time.perf_counter()
        try:
            # Claude 3.5 Sonnet supports up to 16384 output tokens with the
            # `max-tokens-3-5-sonnet-2024-07-15` beta header (sent by _do_call_anthropic).
            result = await self._call_invoice(messages, max_tokens=16384)
        except Exception as e:
            logger.error(
                f"Invoice Pass 2 FAILED after {int((time.perf_counter() - t_p2) * 1000)}ms: "
                f"{type(e).__name__}: {e}"
            )
            raise  # propagate so endpoint can show proper error message
        logger.info(f"Invoice Pass 2 DONE in {int((time.perf_counter() - t_p2) * 1000)}ms")

        # Try resilient parser — returns [] or raises on total failure.
        products: List[dict] = []
        try:
            products = _parse_json_resilient(result or "", tag="pass2")
        except json.JSONDecodeError as e:
            logger.warning(
                f"Invoice Pass 2 JSON TOTAL FAIL: {e}. Resp_len={len(result) if result else 0}, "
                f"tail={result[-200:] if result else 'empty'!r}"
            )

        if products:
            logger.info(
                f"Invoice TOTAL: {len(products)} products in "
                f"{int((time.perf_counter() - t_total) * 1000)}ms "
                f"(from {len(images_bytes)} photo(s))"
            )
            # Log sample of first 5 and last 2 to diagnose hallucinations/wrong matches
            _sample_hi = products[:5]
            _sample_lo = products[-2:] if len(products) > 7 else []
            for i, p in enumerate(_sample_hi):
                logger.info(
                    f"  [{i}] name={(p.get('name') or '')[:60]!r} "
                    f"qty={p.get('quantity')} unit={p.get('unit')} "
                    f"price={p.get('purchase_price')} art={p.get('article')}"
                )
            for i, p in enumerate(_sample_lo, start=len(products) - len(_sample_lo)):
                logger.info(
                    f"  [{i}] name={(p.get('name') or '')[:60]!r} "
                    f"qty={p.get('quantity')} unit={p.get('unit')} "
                    f"price={p.get('purchase_price')} art={p.get('article')}"
                )
            return products

        # Fallback: parse EVERY image separately — covers both JSON total failure and
        # 0-product recovery. Previously only the first image was tried, which silently
        # lost products on multi-page invoices with truncated or malformed JSON.
        logger.info(f"Fallback: parsing all {len(images_bytes)} images individually")
        fb_products: List[dict] = []
        for i, img_bytes in enumerate(images_bytes, start=1):
            try:
                t_i = time.perf_counter()
                partial = await self.parse_invoice_from_image(img_bytes)
                logger.info(
                    f"  Fallback image {i}/{len(images_bytes)}: "
                    f"{len(partial)} products in "
                    f"{int((time.perf_counter() - t_i) * 1000)}ms"
                )
                fb_products.extend(partial)
            except Exception as fe:
                logger.error(f"  Fallback image {i} failed: {fe}")
                continue
        logger.info(
            f"Invoice TOTAL (fallback): {len(fb_products)} products in "
            f"{int((time.perf_counter() - t_total) * 1000)}ms"
        )
        return fb_products

    async def parse_invoice_from_image(self, image_bytes: bytes) -> List[dict]:
        """Parse invoice by sending image directly to Claude vision (when OCR is unavailable)."""
        image_bytes = _compress_image(image_bytes)
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
- category: string|null — выбери наиболее конкретную категорию из: Кабели и переходники, Зарядные устройства, Аксессуары для телефонов, Наушники и аудио, Компьютерная техника, Электроника, Молочные продукты, Мясо и птица, Напитки, Алкоголь, Хлеб и выпечка, Бакалея, Кондитерские изделия, Снеки, Консервы, Овощи и фрукты, Замороженные продукты, Бытовая химия, Средства гигиены, Косметика и парфюмерия, Бытовая техника, Одежда и обувь, Игрушки, Зоотовары, Автотовары, Канцелярия, Медицинские товары, Табак и вейп, Прочее. Используй «Прочее» только если ничего не подходит.

Правила:
- Нормализуй названия: правильный регистр, убери лишние символы и коды
- Если одна колонка цен — это purchase_price
- Игнорируй строки: итого, НДС, сумма, заголовки колонок, реквизиты поставщика

Верни только JSON массив без пояснений. Если товаров нет — []"""

        messages = [{
            "role": "user",
            "content": [
                self._invoice_img_block(base64_image),
                {"type": "text", "text": prompt},
            ],
        }]
        try:
            content = await self._call_invoice(messages, max_tokens=4096)
            return _parse_json_resilient(content or "", tag="single_img")
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
- category: выбери наиболее конкретную: Кабели и переходники/Зарядные устройства/Аксессуары для телефонов/Наушники и аудио/Компьютерная техника/Электроника/Напитки/Молочные продукты/Мясо и птица/Хлеб и выпечка/Бакалея/Кондитерские изделия/Снеки/Алкоголь/Бытовая химия/Средства гигиены/Косметика и парфюмерия/Одежда и обувь/Зоотовары/Автотовары/Табак и вейп/Прочее
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
- category: выбери наиболее конкретную: Кабели и переходники/Зарядные устройства/Аксессуары для телефонов/Наушники и аудио/Компьютерная техника/Электроника/Напитки/Молочные продукты/Мясо и птица/Хлеб и выпечка/Бакалея/Кондитерские изделия/Снеки/Алкоголь/Бытовая химия/Средства гигиены/Косметика и парфюмерия/Одежда и обувь/Зоотовары/Автотовары/Табак и вейп/Прочее

Верни ТОЛЬКО JSON без пояснений:
{{"name":"...","price":null,"purchase_price":null,"barcode":null,"article":null,"category":null,"quantity":1,"unit":"шт","description":null}}"""

        try:
            content = await self._call([{"role": "user", "content": prompt}], max_tokens=200, fast=True)
            return json.loads(_strip_json(content))
        except Exception as e:
            logger.error(f"AI text extraction error: {e}")
            return {"name": text[:100]}


# ── Global singleton ──────────────────────────────────────────────────────────
_ai_service_instance: Optional["AIService"] = None


def get_ai_service() -> "AIService":
    global _ai_service_instance
    if _ai_service_instance is None:
        _ai_service_instance = AIService()
    return _ai_service_instance


def reload_ai_service() -> "AIService":
    global _ai_service_instance
    _ai_service_instance = AIService()
    logger.info("AIService singleton reloaded (proxy config change)")
    return _ai_service_instance
