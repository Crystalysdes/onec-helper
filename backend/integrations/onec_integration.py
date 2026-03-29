import base64
import json
from typing import List, Optional, Tuple
from datetime import datetime

import httpx
from loguru import logger


class OneCClient:
    """Client for 1C:Enterprise REST API (OData protocol)."""

    def __init__(self, url: str, username: str, password: str):
        self.base_url = url.rstrip("/")
        self.auth = (username, password)
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._price_type_key: str | None = None  # cached price type guid

    def _get_auth_header(self) -> dict:
        credentials = f"{self.auth[0]}:{self.auth[1]}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    async def _request(
        self, method: str, path: str, extra_headers: dict = None, **kwargs
    ) -> Tuple[bool, Optional[dict]]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {**self._headers, **self._get_auth_header(), **(extra_headers or {})}
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                response = await client.request(
                    method, url, headers=headers, **kwargs
                )
                if response.status_code in (200, 201, 204):
                    if response.content:
                        return True, response.json()
                    return True, {}
                logger.warning(
                    f"1C API error {response.status_code}: {response.text[:200]}"
                )
                return False, {"error": response.text[:600], "status": response.status_code}
        except httpx.ConnectError as e:
            logger.error(f"1C connection error: {e}")
            return False, {"error": f"Ошибка подключения: {str(e)}"}
        except Exception as e:
            logger.error(f"1C request error: {e}")
            return False, {"error": str(e)}

    async def test_connection(self) -> Tuple[bool, str]:
        """Test connection to 1C system."""
        success, data = await self._request("GET", "odata/standard.odata/")
        if success:
            entities = data.get("value", []) if isinstance(data, dict) else []
            if not entities:
                return True, (
                    "Подключение установлено, но объекты 1С не опубликованы через OData. "
                    "Откройте 1С → Администрирование → найдите «Настройка автоматического REST-сервиса» "
                    "и отметьте нужные объекты (Номенклатура, Товары на складах, Цены)."
                )
            return True, f"Подключение к 1С успешно установлено. Доступно объектов: {len(entities)}"
        error = data.get("error", "Неизвестная ошибка") if data else "Нет ответа"
        return False, f"Ошибка подключения к 1С: {error}"

    async def get_products(
        self, limit: int = 100, offset: int = 0
    ) -> Tuple[bool, List[dict]]:
        """Fetch products (nomenclature) from 1C."""
        base_path = f"odata/standard.odata/Catalog_Номенклатура"
        attempts = [
            f"{base_path}?$format=json&$top={limit}&$skip={offset}&$filter=IsFolder eq false",
            f"{base_path}?$format=json&$top={limit}&$skip={offset}",
        ]
        success, data = False, {}
        for path in attempts:
            success, data = await self._request("GET", path)
            if success:
                break
        if not success:
            err = data.get("error", str(data)) if isinstance(data, dict) else str(data)
            logger.warning(f"get_products failed: {err}")
            return False, []

        items = data.get("value", []) if isinstance(data, dict) else []
        products = []
        for item in items:
            if item.get("IsFolder") or item.get("DeletionMark"):
                continue
            article = item.get("Артикул", "").strip() or item.get("Code", "").strip()
            products.append({
                "onec_id": item.get("Ref_Key"),
                "article": article,
                "name": item.get("Description", ""),
                "code": item.get("Code", ""),
                "full_name": item.get("НаименованиеПолное", ""),
            })
        return True, products

    async def get_products_raw_error(self, limit: int = 5) -> str:
        """Return raw error text from get_products attempt for diagnostics."""
        path = f"odata/standard.odata/Catalog_Номенклатура?$format=json&$top={limit}"
        success, data = await self._request("GET", path)
        if success:
            return f"OK: {len(data.get('value', []))} items"
        return f"HTTP {data.get('status', '?')}: {data.get('error', str(data))[:300]}"

    async def get_barcodes(self) -> dict:
        """Fetch all barcodes. Returns dict: onec_id -> barcode string."""
        entities_to_try = [
            "Catalog_ШтрихкодыНоменклатуры",
            "Catalog_НоменклатураШтрихкоды",
            "InformationRegister_ШтрихкодыНоменклатуры",
            "InformationRegister_Штрихкоды",
        ]
        owner_fields = ["Владелец_Key", "Owner_Key", "Номенклатура_Key"]
        bc_fields = ["Штрихкод", "НомерШтрихкода", "Code"]

        for entity in entities_to_try:
            path = f"odata/standard.odata/{entity}?$format=json&$top=10000"
            success, data = await self._request("GET", path)
            if not success:
                continue
            items = data.get("value", []) if isinstance(data, dict) else []
            if not items:
                continue
            result = {}
            for item in items:
                oid = ""
                for of in owner_fields:
                    if of in item and item[of]:
                        oid = str(item[of]).strip("{}")
                        break
                bc = ""
                for bf in bc_fields:
                    if bf in item and str(item[bf]).strip().isdigit():
                        bc = str(item[bf]).strip()
                        break
                if oid and bc and oid not in result:
                    result[oid] = bc
            logger.info(f"1C barcodes loaded from {entity}: {len(result)} entries")
            return result

        # Fallback: read Штрихкод field directly from Catalog_Номенклатура
        path = ("odata/standard.odata/Catalog_Номенклатура"
                "?$format=json&$top=50000&$select=Ref_Key,Штрихкод")
        ok, data = await self._request("GET", path)
        if ok and isinstance(data, dict):
            result = {}
            for item in data.get("value", []):
                oid = str(item.get("Ref_Key", "")).strip("{}")
                bc = str(item.get("Штрихкод", "")).strip()
                if oid and bc and bc.isdigit():
                    result[oid] = bc
            if result:
                logger.info(f"1C barcodes loaded from Catalog_Ном/Штрихкод: {len(result)} entries")
                return result
        logger.warning("1C barcodes: no barcode source found in OData")
        return {}

    async def get_entities(self) -> List[str]:
        """Return list of all published OData entity names."""
        success, data = await self._request("GET", "odata/standard.odata/?$format=json")
        if not success or not isinstance(data, dict):
            return []
        return [e.get("name", "") for e in data.get("value", []) if e.get("name")]

    async def get_all_prices(self) -> dict:
        """Fetch retail prices from 1C. Returns {onec_id: price}."""
        retail, _ = await self._classify_all_prices()
        return retail

    async def get_purchase_prices(self) -> dict:
        """Fetch purchase prices from 1C. Returns {onec_id: price}."""
        _, purchase = await self._classify_all_prices()
        return purchase

    async def _classify_all_prices(self) -> tuple[dict, dict]:
        """Single-pass fetch of all price records; classify by type name.

        Returns (retail_prices, purchase_prices) each as {onec_id: price}.
        Retail hints: 'розн'
        Purchase hints: 'закуп', 'учет', 'purchase', 'cost'
        Unknown types: highest price → retail, second highest → purchase.
        """
        RETAIL_HINTS = ("розн", "продаж", "основн", "retail", "base")
        PURCHASE_HINTS = ("закуп", "учет", "purchase", "cost", "себест", "поставщик", "приход", "входящ", "опт")

        type_names: dict[str, str] = {}
        types = await self.get_price_types()
        for t in types:
            key = str(t.get("Ref_Key", "")).strip("{}")
            name = t.get("Description", "").lower()
            if key:
                type_names[key] = name

        for register in ("InformationRegister_ЦеныНоменклатуры", "InformationRegister_Цены"):
            path = (
                f"odata/standard.odata/{register}"
                f"?$format=json&$top=50000"
                f"&$select=Номенклатура_Key,Цена,ВидЦены_Key"
            )
            ok, data = await self._request("GET", path)
            if not ok or not isinstance(data, dict) or not data.get("value"):
                continue

            # accumulate per-product by price type
            by_product: dict[str, list[tuple[float, str]]] = {}
            for item in data["value"]:
                oid = str(item.get("Номенклатура_Key", "")).strip("{}")
                price = item.get("Цена") or item.get("Price")
                type_key = str(item.get("ВидЦены_Key") or "").strip("{}")
                if oid and price is not None:
                    by_product.setdefault(oid, []).append((float(price), type_key))

            retail: dict = {}
            purchase: dict = {}
            for oid, entries in by_product.items():
                # Pass 1: named types take priority
                for price_val, type_key in entries:
                    name = type_names.get(type_key, "")
                    if any(h in name for h in RETAIL_HINTS):
                        retail[oid] = price_val
                    elif any(h in name for h in PURCHASE_HINTS):
                        purchase[oid] = price_val

                # Pass 2: unknown types fill whatever is still missing
                unknowns = sorted(
                    [pv for pv, tk in entries
                     if not any(h in type_names.get(tk, "") for h in RETAIL_HINTS)
                     and not any(h in type_names.get(tk, "") for h in PURCHASE_HINTS)],
                    reverse=True,  # highest first
                )
                for price_val in unknowns:
                    if oid not in retail:
                        retail[oid] = price_val
                    elif oid not in purchase and price_val != retail[oid]:
                        purchase[oid] = price_val
                        break

            logger.info(f"1C prices classified from {register}: retail={len(retail)} purchase={len(purchase)}")
            return retail, purchase
        return {}, {}

    async def set_price(self, onec_id: str, price: float,
                        price_type_name: str | None = None) -> bool:
        """Write price for a product in 1C.

        price_type_name: hint to select price type, e.g. 'розн' for retail,
                         'учет' / 'закуп' for purchase/accounting.
        """
        onec_id = str(onec_id).strip("{}")
        from datetime import datetime as _dt
        period = _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        _zero = "00000000-0000-0000-0000-000000000000"
        if price_type_name:
            price_type_key = await self._get_price_type_key_by_name(price_type_name)
            if price_type_key is None:
                # Fallback: pick by position among available types
                _all_types = await self.get_price_types()
                _RETAIL_H = ("розн", "продаж", "основн", "retail")
                _PURCH_H = ("закуп", "учет", "purchase", "cost", "поставщик", "приход")
                _is_purch = any(h in price_type_name.lower() for h in _PURCH_H)
                if _is_purch and _all_types:
                    non_retail = [t for t in _all_types
                                  if not any(h in t.get("Description", "").lower() for h in _RETAIL_H)]
                    price_type_key = str((non_retail[0] if non_retail else _all_types[-1]).get("Ref_Key", "")).strip("{}")
                    logger.warning(f"1C set_price: '{price_type_name}' not found, using fallback: {(non_retail[0] if non_retail else _all_types[-1]).get('Description')}")
                elif _all_types:
                    price_type_key = str(_all_types[0].get("Ref_Key", "")).strip("{}")
                    logger.warning(f"1C set_price: '{price_type_name}' not found, using fallback: {_all_types[0].get('Description')}")
                else:
                    logger.warning(f"1C set_price: price type '{price_type_name}' not found, no types available — skipping")
                    return False
        else:
            price_type_key = await self._get_or_fetch_price_type_key()
        vid_key = price_type_key or _zero

        # ── 1. Document_УстановкаЦенНоменклатуры (tabular section = Запасы)
        org_key = await self._get_org_key()
        row = {"LineNumber": 1, "Номенклатура_Key": onec_id, "Цена": price,
               "Характеристика_Key": _zero, "ВидЦены_Key": vid_key}
        doc = {"Date": period, "ВидЦены_Key": vid_key,
                "ЗаписыватьНовыеЦеныПоверхУстановленных": True,
                "Комментарий": "Авто из 1С Хелпер",
                "Запасы": [row]}
        if org_key:
            doc["Организация_Key"] = org_key
        ok, resp = await self._request(
            "POST", "odata/standard.odata/Document_УстановкаЦенНоменклатуры", json=doc
        )
        if ok and isinstance(resp, dict):
            ref_key = str(resp.get("Ref_Key", "")).strip("{}")
            if ref_key:
                # Conduct via (guid)/Post
                ok2, resp2 = await self._request(
                    "POST",
                    f"odata/standard.odata/Document_УстановкаЦенНоменклатуры(guid'{ref_key}')/Post"
                )
                if ok2:
                    logger.info(f"1C price Document posted: {onec_id} → {price}")
                    # Mark for deletion so it doesn’t clutter the 1C journal
                    await self._request(
                        "PATCH",
                        f"odata/standard.odata/Document_УстановкаЦенНоменклатуры(guid'{ref_key}')",
                        json={"ПометкаУдаления": True}
                    )
                    return True
                logger.warning(f"1C price Document Post failed for {ref_key}: {resp2}")
        logger.warning(f"1C price Document_УстановкаЦен/Запасы failed: {resp}")

        # ── 2. InformationRegister fallback
        period0 = "0001-01-01T00:00:00"
        registers = ("InformationRegister_ЦеныНоменклатуры", "InformationRegister_Цены")
        for register in registers:
            filter_parts = [f"Номенклатура_Key eq guid'{onec_id}'"]
            if price_type_key:
                filter_parts.append(f"ВидЦены_Key eq guid'{price_type_key}'")
            path = (
                f"odata/standard.odata/{register}"
                f"?$format=json&$filter={' and '.join(filter_parts)}&$top=1"
            )
            success, data = await self._request("GET", path)
            if success:
                items = data.get("value", []) if isinstance(data, dict) else []
                if items:
                    item = items[0]
                    pt_key = item.get("ВидЦены_Key") or price_type_key
                    old_period = item.get("Период", period)
                    key_parts = [f"Период=datetime'{old_period}'",
                                 f"Номенклатура_Key=guid'{onec_id}'"]
                    if pt_key:
                        key_parts.append(f"ВидЦены_Key=guid'{pt_key}'")
                    patch_payload: dict = {"Цена": price, "Период": period}
                    if item.get("Валюта_Key"):
                        patch_payload["Валюта_Key"] = item["Валюта_Key"]
                    ok, _ = await self._request(
                        "PATCH",
                        f"odata/standard.odata/{register}({','.join(key_parts)})",
                        json=patch_payload,
                    )
                    if ok:
                        logger.info(f"1C price updated ({register}): {onec_id} → {price}")
                        return True

            for post_payload in [
                {"Период": period, "Номенклатура_Key": onec_id, "Цена": price,
                 "ВидЦены_Key": vid_key, "Характеристика_Key": _zero, "Упаковка_Key": _zero},
                {"Период": period, "Номенклатура_Key": onec_id, "Цена": price, "ВидЦены_Key": vid_key},
                {"Период": period0, "Номенклатура_Key": onec_id, "Цена": price,
                 "ВидЦены_Key": vid_key, "Характеристика_Key": _zero, "Упаковка_Key": _zero},
                {"Период": period0, "Номенклатура_Key": onec_id, "Цена": price, "ВидЦены_Key": vid_key},
            ]:
                ok, resp = await self._request(
                    "POST", f"odata/standard.odata/{register}", json=post_payload
                )
                if ok:
                    logger.info(f"1C price created ({register}): {onec_id} → {price}")
                    return True
                logger.warning(f"1C price POST ({register}, keys={list(post_payload)}): {resp}")

        logger.warning(f"1C price set failed for onec_id={onec_id}, price={price}")
        return False

    async def get_product_prices(self, product_ids: List[str]) -> dict:
        """Get current prices for products from 1C. Returns empty dict if register not published."""
        prices = {}
        for register in ("InformationRegister_ЦеныНоменклатуры", "InformationRegister_Цены"):
            for pid in product_ids:
                path = (
                    f"odata/standard.odata/{register}"
                    f"?$format=json&$filter=Номенклатура_Key eq guid'{pid}'"
                    f"&$select=Цена,Валюта_Key&$top=1"
                )
                success, data = await self._request("GET", path)
                if success and data:
                    items = data.get("value", [])
                    if items:
                        prices[pid] = items[0].get("Цена", 0)
            if prices:
                break
        return prices

    async def get_stock_balances(self, store_id: str = None) -> Tuple[bool, List[dict]]:
        """Get stock balances from 1C. Tries multiple register names for different 1C configs."""
        registers = [
            ("InformationRegister_ОстаткиТоваров", "Количество", "СтруктурнаяЕдиница", False),
            ("AccumulationRegister_ТоварыНаСкладах/Balance", "КоличествоБаланс", "Склад_Key", True),
            ("AccumulationRegister_ЗапасыКПоступлениюНаСклады/Balance", "КоличествоБаланс", "Склад_Key", True),
        ]
        for reg_path, qty_field, wh_field, wh_is_guid in registers:
            path = f"odata/standard.odata/{reg_path}?$format=json&$select=Номенклатура_Key,{qty_field}"
            if store_id:
                if wh_is_guid:
                    path += f"&$filter={wh_field} eq guid'{store_id}'"
                else:
                    path += f"&$filter={wh_field} eq '{store_id}'"
            success, data = await self._request("GET", path)
            if success:
                items = data.get("value", []) if isinstance(data, dict) else []
                balances = [
                    {
                        "onec_id": str(item.get("Номенклатура_Key", "")),
                        "quantity": item.get(qty_field, 0) or 0,
                    }
                    for item in items
                    if item.get("Номенклатура_Key")
                ]
                return True, balances
        return False, []

    async def get_or_create_category(self, category_name: str) -> Optional[str]:
        """Find or create a folder (category) in 1C Nomenclature catalog."""
        safe_name = category_name.replace("'", "'")
        path = (
            f"odata/standard.odata/Catalog_Номенклатура"
            f"?$format=json&$filter=Description eq '{safe_name}' and IsFolder eq true"
            f"&$select=Ref_Key,Description&$top=1"
        )
        success, data = await self._request("GET", path)
        if success:
            items = data.get("value", []) if isinstance(data, dict) else []
            if items:
                key = items[0].get("Ref_Key")
                logger.info(f"1C category found: '{category_name}' → {key}")
                return key

        payload = {"Description": category_name, "IsFolder": True}
        success, data = await self._request(
            "POST", "odata/standard.odata/Catalog_Номенклатура", json=payload
        )
        if success and data and data.get("Ref_Key"):
            key = data["Ref_Key"]
            logger.info(f"1C category created: '{category_name}' → {key}")
            return key
        logger.warning(f"1C category create failed for '{category_name}': {data}")
        return None

    async def find_product_by_name(self, name: str) -> Optional[str]:
        """Search 1C Catalog_Номенклатура by Description, return Ref_Key GUID or None."""
        import urllib.parse
        q = urllib.parse.quote(name.replace("'", "''"))
        ok, data = await self._request(
            "GET",
            f"odata/standard.odata/Catalog_Номенклатура?$format=json&$filter=Description eq '{q}'&$select=Ref_Key&$top=1"
        )
        if ok and isinstance(data, dict):
            items = data.get("value", [])
            if items:
                return str(items[0].get("Ref_Key", "")).strip("{}")
        return None

    async def create_product(self, product) -> Tuple[bool, Optional[dict]]:
        """Create a new product (nomenclature) in 1C."""
        payload = {
            "Description": product.name,
            "Артикул": product.article or "",
        }
        category = getattr(product, "category", None)
        if category:
            parent_key = await self.get_or_create_category(category)
            if parent_key:
                payload["Parent_Key"] = parent_key
        success, data = await self._request(
            "POST",
            "odata/standard.odata/Catalog_Номенклатура",
            json=payload,
        )
        return success, data

    async def update_product(
        self, onec_id: str, product
    ) -> Tuple[bool, Optional[dict]]:
        """Update existing product in 1C."""
        payload = {
            "Description": product.name,
            "Артикул": product.article or "",
        }
        barcode = getattr(product, "barcode", None)
        if barcode and str(barcode).strip():
            payload["Штрихкод"] = str(barcode).strip()
        category = getattr(product, "category", None)
        if category:
            parent_key = await self.get_or_create_category(category)
            if parent_key:
                payload["Parent_Key"] = parent_key
        success, data = await self._request(
            "PATCH",
            f"odata/standard.odata/Catalog_Номенклатура(guid'{onec_id}')",
            json=payload,
        )
        return success, data

    @staticmethod
    def _detect_barcode_type(barcode: str) -> str:
        digits_only = barcode.strip().isdigit()
        length = len(barcode.strip())
        if digits_only and length == 13:
            return "EAN13"
        if digits_only and length == 8:
            return "EAN8"
        if digits_only and length == 12:
            return "EAN13"  # UPC-A treated as EAN13
        return "Code128"

    async def get_price_types(self) -> list:
        """Return list of price type records from 1C (Catalog_ВидыЦен or equivalent)."""
        for entity in ("Catalog_ВидыЦен", "Catalog_ТипыЦен", "Catalog_ВидЦен"):
            success, data = await self._request(
                "GET",
                f"odata/standard.odata/{entity}?$format=json&$top=50"
                f"&$filter=DeletionMark eq false&$select=Ref_Key,Description",
            )
            if success and isinstance(data, dict) and data.get("value"):
                return data["value"]
        return []

    async def _get_or_fetch_price_type_key(self) -> str | None:
        """Return cached price type key, fetching from 1C if needed.

        Strategy:
          1. Try Catalog_ВидыЦен (may not be published).
          2. Fallback: read ONE existing record from the price register and
             extract ВидЦены_Key from it — works even when the catalog is not published.
        """
        if self._price_type_key:
            return self._price_type_key

        # ── 1. Catalog-based lookup ──────────────────────────────────────────
        types = await self.get_price_types()
        if types:
            retail = next(
                (t for t in types if "розн" in t.get("Description", "").lower()), None
            )
            chosen = retail or types[0]
            self._price_type_key = chosen.get("Ref_Key")
            logger.info(f"1C price type (catalog): {chosen.get('Description')} → {self._price_type_key}")
            return self._price_type_key

        # ── 2. Try to create "Розничная цена" price type if catalog is writable
        for entity in ("Catalog_ВидыЦен", "Catalog_ВидЦен"):
            ok, data = await self._request(
                "POST",
                f"odata/standard.odata/{entity}",
                json={"Description": "Розничная цена"},
            )
            if ok and isinstance(data, dict) and data.get("Ref_Key"):
                self._price_type_key = str(data["Ref_Key"]).strip("{}")
                logger.info(f"1C price type created: Розничная цена → {self._price_type_key}")
                return self._price_type_key

        # ── 3. Fallback: read ВидЦены_Key from an existing price record ──────
        for register in ("InformationRegister_ЦеныНоменклатуры", "InformationRegister_Цены"):
            ok, data = await self._request(
                "GET",
                f"odata/standard.odata/{register}?$format=json&$top=1"
                f"&$select=ВидЦены_Key,ТипЦены_Key",
            )
            if ok and isinstance(data, dict):
                items = data.get("value", [])
                if items:
                    key = (items[0].get("ВидЦены_Key") or items[0].get("ТипЦены_Key"))
                    if key and key != "00000000-0000-0000-0000-000000000000":
                        self._price_type_key = str(key)
                        logger.info(f"1C price type (from register {register}): {self._price_type_key}")
                        return self._price_type_key

        logger.warning("1C price type key not found — will attempt price write without ВидЦены_Key")
        return None

    async def _get_price_type_key_by_name(self, name_hint: str) -> str | None:
        """Return Ref_Key of the price type whose Description contains name_hint (case-insensitive)."""
        _RETAIL_ALIASES = ("розн", "продаж", "основн", "retail", "base")
        _PURCHASE_ALIASES = ("закуп", "учет", "purchase", "cost", "себест", "поставщик", "приход", "входящ", "опт")
        types = await self.get_price_types()
        hint = name_hint.lower()
        match = next((t for t in types if hint in t.get("Description", "").lower()), None)
        if match:
            return str(match.get("Ref_Key", "")).strip("{}")
        aliases = _RETAIL_ALIASES if hint in _RETAIL_ALIASES else (
            _PURCHASE_ALIASES if hint in _PURCHASE_ALIASES else ()
        )
        for alias in aliases:
            match = next((t for t in types if alias in t.get("Description", "").lower()), None)
            if match:
                logger.debug(f"1C price type '{name_hint}' matched via alias '{alias}': {match.get('Description')}")
                return str(match.get("Ref_Key", "")).strip("{}")
        available = [t.get("Description", "") for t in types]
        logger.warning(f"1C price type '{name_hint}' not found. Available: {available}")
        return None

    async def _get_org_key(self) -> str | None:
        """Return GUID of the first organisation from 1C."""
        if hasattr(self, "_org_key_cache") and self._org_key_cache:
            return self._org_key_cache
        ok, data = await self._request(
            "GET", "odata/standard.odata/Catalog_Организации?$format=json&$top=1"
        )
        if ok and isinstance(data, dict) and data.get("value"):
            self._org_key_cache = str(data["value"][0].get("Ref_Key", "")).strip("{}")
            return self._org_key_cache
        return None

    async def _get_warehouse_key(self) -> str | None:
        """Return GUID of the first warehouse (Склад) from 1C."""
        if hasattr(self, "_warehouse_key_cache") and self._warehouse_key_cache:
            return self._warehouse_key_cache
        for catalog in ("Catalog_СтруктурныеЕдиницы", "Catalog_Склады", "Catalog_МестаХранения"):
            ok, data = await self._request(
                "GET", f"odata/standard.odata/{catalog}?$format=json&$top=1&$filter=IsFolder eq false"
            )
            if ok and isinstance(data, dict) and data.get("value"):
                self._warehouse_key_cache = str(data["value"][0].get("Ref_Key", "")).strip("{}")
                logger.info(f"1C warehouse ({catalog}): {self._warehouse_key_cache}")
                return self._warehouse_key_cache
        return None

    async def _get_account_key(self, codes: list[str], cache_attr: str) -> str | None:
        """Generic: find a 1C account by trying multiple codes across chart-of-accounts entities."""
        cached = getattr(self, cache_attr, None)
        if cached:
            return cached
        for chart in ("ChartOfAccounts_Хозрасчетный", "ChartOfAccounts_Управленческий"):
            for code in codes:
                ok, data = await self._request(
                    "GET",
                    f"odata/standard.odata/{chart}"
                    f"?$format=json&$filter=Code eq '{code}'&$top=1&$select=Ref_Key,Code"
                )
                if ok and isinstance(data, dict) and data.get("value"):
                    key = str(data["value"][0].get("Ref_Key", "")).strip("{}")
                    if key and key != "00000000-0000-0000-0000-000000000000":
                        setattr(self, cache_attr, key)
                        logger.info(f"1C account {codes[0]} ({chart}): {key}")
                        return key
        return None

    async def _get_goods_account_key(self) -> str | None:
        """Account 41.02/41.01/41 — debit side for stock receipt."""
        return await self._get_account_key(["41.02", "41.01", "41"], "_goods_account_cache")

    async def _get_income_account_key(self) -> str | None:
        """Account 91.01/91/94 — credit side for surplus stock posting."""
        return await self._get_account_key(["91.01", "91", "94"], "_income_account_cache")

    async def _get_stock_accounts(self, onec_id: str) -> tuple[str | None, str | None]:
        """Return (debit_key, credit_key) for stock receipt posting.

        Sources tried in order:
        0. Root OData endpoint — discover any published ChartOfAccounts entity names
        1. InformationRegister_СчетаУчетаНоменклатуры (per-product settings)
        2. AccountingRegister_ЖурналПроводок (GUIDs from existing transactions)
        3. ChartOfAccounts — broad fetch, match by code prefix, fallback to first account
        """
        _zero = "00000000-0000-0000-0000-000000000000"

        def _valid(v) -> str | None:
            s = str(v or "").strip("{}")
            return s if (s and s != _zero) else None

        DEBIT_FIELDS  = ["СчетДт_Key", "СчетУчетаДебет_Key", "СчетУчетаТовары_Key",
                         "СчетУчетаДоходов_Key", "СчетУчета_Key"]
        CREDIT_FIELDS = ["СчетКт_Key", "СчетУчетаКредит_Key", "СчетУчетаРасходов_Key"]

        # ── Source 0.0: Read accounting accounts directly from Catalog_Номенклатура ──
        # The product catalog item has СчетУчетаЗапасов_Key — exactly the debit account needed
        ok_n, nom = await self._request(
            "GET",
            f"odata/standard.odata/Catalog_Номенклатура(guid'{onec_id}')"
            f"?$format=json&$select=СчетУчетаЗапасов_Key,СчетУчетаДоходов_Key,"
            f"СчетУчетаНДСПоПриобретеннымЦенностям_Key,СчетУчетаЗатрат_Key"
        )
        debit_from_nom, credit_from_nom = None, None
        if ok_n and isinstance(nom, dict):
            debit_from_nom = _valid(nom.get("СчетУчетаЗапасов_Key"))
            credit_from_nom = (_valid(nom.get("СчетУчетаДоходов_Key"))
                               or _valid(nom.get("СчетУчетаНДСПоПриобретеннымЦенностям_Key"))
                               or _valid(nom.get("СчетУчетаЗатрат_Key")))
            logger.info(f"1C Catalog_Номенклатура accounts: debit={debit_from_nom} credit={credit_from_nom}")
            if debit_from_nom:
                return debit_from_nom, credit_from_nom

        # ── Source 0.1: Find any catalog item with СчетУчетаЗапасов_Key set ──
        _zero_filter = "00000000-0000-0000-0000-000000000000"
        if not getattr(self, "_global_debit_cache", None):
            # Try InformationRegister_СчетаУчетаНоменклатуры first
            ok_ir, ir_data = await self._request(
                "GET",
                "odata/standard.odata/InformationRegister_СчетаУчетаНоменклатуры"
                "?$format=json&$top=1"
            )
            if ok_ir and isinstance(ir_data, dict) and ir_data.get("value"):
                row = ir_data["value"][0]
                logger.info(f"1C СчетаУчетаНоменклатуры fields: {list(row.keys())}")
                for fld in ("СчетУчетаЗапасов_Key", "СчетДт_Key", "СчетУчетаТовары_Key", "СчетУчета_Key"):
                    v = _valid(row.get(fld))
                    if v:
                        self._global_debit_cache = v
                        logger.info(f"1C global debit from СчетаУчетаНоменклатуры.{fld}: {v}")
                        break

            if not getattr(self, "_global_debit_cache", None):
                # Fall back: find any Catalog_Номенклатура with non-zero СчетУчетаЗапасов_Key
                ok_any, any_data = await self._request(
                    "GET",
                    f"odata/standard.odata/Catalog_Номенклатура"
                    f"?$format=json&$top=50&$select=СчетУчетаЗапасов_Key,СчетУчетаДоходов_Key"
                    f"&$filter=IsFolder eq false"
                )
                if ok_any and isinstance(any_data, dict):
                    for item in any_data.get("value", []):
                        v = _valid(item.get("СчетУчетаЗапасов_Key"))
                        if v:
                            self._global_debit_cache = v
                            logger.info(f"1C global debit from catalog scan: {v}")
                            break

        global_debit = getattr(self, "_global_debit_cache", None)
        if global_debit:
            return global_debit, credit_from_nom

        # ── Source 0: Discover published ChartOfAccounts from root OData endpoint ──
        if not getattr(self, "_discovered_charts", None):
            ok0, root = await self._request("GET", "odata/standard.odata/?$format=json")
            if ok0 and isinstance(root, dict):
                names = [e.get("name", "") for e in root.get("value", [])]
                self._discovered_charts = [
                    n for n in names
                    if n.startswith("ChartOfAccounts_") or "ПланСчетов" in n
                ]
                if self._discovered_charts:
                    logger.info(f"1C discovered chart entities: {self._discovered_charts}")
                else:
                    logger.warning("1C: no ChartOfAccounts entities published in OData")
                    self._discovered_charts = []
        discovered_charts = getattr(self, "_discovered_charts", [])

        # ── Source 1: InformationRegister_СчетаУчетаНоменклатуры ─────────────
        for reg in ("InformationRegister_СчетаУчетаНоменклатуры",
                    "InformationRegister_СчетаУчетаНоменклатурыПоОрганизациям"):
            for suffix in (
                f"?$format=json&$top=1&$filter=Номенклатура_Key eq guid'{onec_id}'",
                "?$format=json&$top=1",
            ):
                ok, data = await self._request("GET", f"odata/standard.odata/{reg}{suffix}")
                if ok and isinstance(data, dict) and data.get("value"):
                    item = data["value"][0]
                    logger.info(f"1C acct reg {reg} fields: {list(item.keys())}")
                    debit  = next((_valid(item.get(f)) for f in DEBIT_FIELDS
                                   if _valid(item.get(f))), None)
                    credit = next((_valid(item.get(f)) for f in CREDIT_FIELDS
                                   if _valid(item.get(f))), None)
                    if debit:
                        logger.info(f"1C stock accounts from {reg}: debit={debit} credit={credit}")
                        return debit, credit

        # ── Source 1.2: Try all published InformationRegisters for account fields ─
        pub_info = getattr(self, "_published_info_registers", None)
        if pub_info is None:
            ok0, root = await self._request("GET", "odata/standard.odata/?$format=json")
            if ok0 and isinstance(root, dict):
                all_n = {e.get("name", "") for e in root.get("value", [])}
                pub_info = {n for n in all_n if n.startswith("InformationRegister_")}
                self._published_info_registers = pub_info
                logger.info(f"1C published InformationRegisters: {sorted(pub_info)}")
            else:
                pub_info = set()
        for ir_name in sorted(pub_info):
            if not any(kw in ir_name for kw in ("Счет", "Учет", "Account")):
                continue
            ok, data = await self._request(
                "GET", f"odata/standard.odata/{ir_name}?$format=json&$top=2"
            )
            if not ok or not isinstance(data, dict) or not data.get("value"):
                continue
            item = data["value"][0]
            logger.info(f"1C IR {ir_name} fields: {list(item.keys())}")
            debit = next((_valid(item.get(f)) for f in DEBIT_FIELDS if _valid(item.get(f))), None)
            if debit:
                credit = next((_valid(item.get(f)) for f in CREDIT_FIELDS if _valid(item.get(f))), None)
                logger.info(f"1C stock accounts from {ir_name}: debit={debit} credit={credit}")
                return debit, credit

        # ── Source 0.5: Tabular section row entities (accessed without $expand) ───────
        for doc_tab in (
            "Document_ОприходованиеЗапасов_Запасы",
            "Document_ОприходованиеТоваров_Товары",
            "Document_ПоступлениеТоваровУслуг_Товары",
        ):
            ok, data = await self._request(
                "GET", f"odata/standard.odata/{doc_tab}?$format=json&$top=3"
            )
            if not ok or not isinstance(data, dict) or not data.get("value"):
                continue
            item = data["value"][0]
            logger.info(f"1C {doc_tab} row fields: {list(item.keys())}")
            debit = next((_valid(item.get(f)) for f in DEBIT_FIELDS if _valid(item.get(f))), None)
            if debit:
                credit = next((_valid(item.get(f)) for f in CREDIT_FIELDS if _valid(item.get(f))), None)
                logger.info(f"1C stock accounts from {doc_tab}: debit={debit} credit={credit}")
                return debit, credit

        # ── Source 0.6: InformationRegister_СуммыДокументов (regulated accounting sums) ──
        ok_sd, data_sd = await self._request(
            "GET",
            "odata/standard.odata/InformationRegister_СуммыДокументовРегламентированныйУчет?$format=json&$top=2"
        )
        if ok_sd and isinstance(data_sd, dict) and data_sd.get("value"):
            item_sd = data_sd["value"][0]
            logger.info(f"1C СуммыДокументов fields: {list(item_sd.keys())}")
            debit = next((_valid(item_sd.get(f)) for f in DEBIT_FIELDS if _valid(item_sd.get(f))), None)
            if debit:
                credit = next((_valid(item_sd.get(f)) for f in CREDIT_FIELDS if _valid(item_sd.get(f))), None)
                logger.info(f"1C stock accounts from СуммыДокументов: debit={debit} credit={credit}")
                return debit, credit

        # ── Source 1.5: Read accounts from existing POSTED documents ─────────────────
        if not getattr(self, "_cached_doc_accounts", None):
            self._cached_doc_accounts = None
            for doc_type, tab in (
                ("Document_ОприходованиеЗапасов", "Запасы"),
                ("Document_ОприходованиеТоваров", "Товары"),
                ("Document_ПоступлениеТоваровУслуг", "Товары"),
            ):
                ok, data = await self._request(
                    "GET",
                    f"odata/standard.odata/{doc_type}"
                    f"?$format=json&$top=3&$filter=Проведен eq true&$expand={tab}"
                )
                if not ok or not isinstance(data, dict):
                    continue
                for doc in data.get("value", []):
                    rows = doc.get(tab, [])
                    for row in rows:
                        row_debit = next((_valid(row.get(f)) for f in DEBIT_FIELDS
                                          if _valid(row.get(f))), None)
                        if row_debit:
                            row_credit = next((_valid(row.get(f)) for f in CREDIT_FIELDS
                                               if _valid(row.get(f))), None)
                            self._cached_doc_accounts = (row_debit, row_credit)
                            logger.info(f"1C stock accounts from existing {doc_type} row: "
                                        f"debit={row_debit} credit={row_credit}")
                            break
                    if self._cached_doc_accounts:
                        break
                if self._cached_doc_accounts:
                    break
        if getattr(self, "_cached_doc_accounts", None):
            return self._cached_doc_accounts

        # ── Source 2: AccountingRegister — read GUIDs from existing transactions ─
        for acc_reg in (
            "AccountingRegister_Управленческий",   # УНФ management accounting (confirmed published)
            "AccountingRegister_Хозрасчетный",     # КА/БУХ
            "AccountingRegister_ЖурналПроводок",   # УНФ older name
        ):
            # First try with $select; if empty/no debit try without $select
            for sel in ("?$format=json&$top=3&$select=СчетДт_Key,СчетКт_Key",
                        "?$format=json&$top=1"):
                ok, data = await self._request(
                    "GET", f"odata/standard.odata/{acc_reg}{sel}"
                )
                if not ok or not isinstance(data, dict):
                    break  # register not published — skip
                if not data.get("value"):
                    continue  # empty result — try other sel variant
                item = data["value"][0]
                if sel.endswith("$top=1"):
                    logger.info(f"1C {acc_reg} sample fields: {list(item.keys())}")
                # Try known debit field names
                debit = next((_valid(item.get(f)) for f in DEBIT_FIELDS
                              if _valid(item.get(f))), None)
                if debit:
                    credit = next((_valid(item.get(f)) for f in CREDIT_FIELDS
                                   if _valid(item.get(f))), None)
                    logger.info(f"1C stock accounts from {acc_reg}: debit={debit} credit={credit}")
                    return debit, credit
                if sel.endswith("$top=1"):
                    break  # already tried all fields, no debit found

        # ── Source 2.5: AccountingRegister_Управленческий — scan debit accounts ──
        # УНФ uses this register; if any transactions exist we can borrow account GUIDs.
        if not getattr(self, "_ar_debit_cache", None):
            for sel_suffix in (
                "?$format=json&$top=5&$select=СчетДт_Key,СчетКт_Key",
                "?$format=json&$top=5",
            ):
                ok_ar, ar_data = await self._request(
                    "GET", f"odata/standard.odata/AccountingRegister_Управленческий{sel_suffix}"
                )
                if not ok_ar or not isinstance(ar_data, dict):
                    break
                for row in ar_data.get("value", []):
                    for fld in ("СчетДт_Key", "Дебет_Key", "СчетУчета_Key"):
                        v = _valid(row.get(fld))
                        if v:
                            self._ar_debit_cache = v
                            logger.info(f"1C AR_Управленческий debit account from {fld}: {v}")
                            break
                    if getattr(self, "_ar_debit_cache", None):
                        break
                if getattr(self, "_ar_debit_cache", None):
                    break
        if getattr(self, "_ar_debit_cache", None):
            return self._ar_debit_cache, None

        # ── Source 3: ChartOfAccounts — no filter, match by code prefix or description ──
        all_charts = (discovered_charts or []) + [
            "ChartOfAccounts_Хозрасчетный", "ChartOfAccounts_Управленческий"
        ]
        for chart in list(dict.fromkeys(all_charts)):
            # Fetch with Description so we can match by keyword for УНФ (word-based codes)
            ok, data = await self._request(
                "GET",
                f"odata/standard.odata/{chart}?$format=json&$top=200"
                f"&$select=Ref_Key,Code,Description&$filter=IsFolder eq false"
            )
            if not ok or not isinstance(data, dict):
                # Retry without filter/select in case of schema differences
                ok, data = await self._request(
                    "GET", f"odata/standard.odata/{chart}?$format=json&$top=200"
                )
                if not ok or not isinstance(data, dict):
                    continue
            all_acc = data.get("value", [])
            logger.info(f"1C {chart}: {len(all_acc)} accounts; "
                        f"sample={[(str(a.get('Code','')), str(a.get('Description',''))[:20]) for a in all_acc[:5]]}")
            if not all_acc:
                continue

            def _find(prefixes: list[str]) -> str | None:
                for pfx in prefixes:
                    m = next((a for a in all_acc
                              if str(a.get("Code", "")).startswith(pfx)), None)
                    if m:
                        return str(m["Ref_Key"]).strip("{}")
                return None

            def _find_by_desc(keywords: list[str]) -> str | None:
                """Match account by Description keyword — for УНФ word-based chart."""
                for kw in keywords:
                    m = next((a for a in all_acc
                              if kw.lower() in str(a.get("Description", "")).lower()), None)
                    if m:
                        return _valid(m.get("Ref_Key"))
                return None

            # 1. Numeric code match (БУХ/КА/УТ standard chart)
            debit  = _find(["41.02", "41.01", "41.2", "41", "10.01", "10"])
            credit = _find(["91.01", "91.1", "91", "94", "99"])
            if debit:
                logger.info(f"1C stock accounts from {chart} by code: debit={debit} credit={credit}")
                return debit, credit

            # 2. Description keyword match (УНФ management chart uses word names)
            debit  = _find_by_desc(["Запас", "Товар", "Матери", "Произво"])
            credit = _find_by_desc(["Выруч", "Доход", "Капитал", "Прибыл"])
            if debit:
                logger.info(f"1C stock accounts from {chart} by description: debit={debit} credit={credit}")
                return debit, credit

            # 3. Last resort: first non-folder non-zero account in the chart
            for a in all_acc:
                key = _valid(a.get("Ref_Key"))
                if key:
                    logger.warning(f"1C stock account: using first available "
                                   f"code={a.get('Code')} desc={str(a.get('Description',''))[:30]} key={key}")
                    return key, None

        # ── Ultimate fallback: use credit account from product as debit ──────────
        # ChartOfAccounts not published → borrow any known account GUID so the
        # posting handler has something to write to AccountingRegister.
        if credit_from_nom:
            logger.warning(
                f"1C _get_stock_accounts: using credit account as debit fallback "
                f"(ChartOfAccounts unpublished): {credit_from_nom}"
            )
            return credit_from_nom, credit_from_nom

        logger.warning("1C _get_stock_accounts: no account found in any source")
        return None, None

    async def _write_off_stock(self, onec_id: str, qty: float, price: float,
                               use_accounting: bool, new_absolute_qty: float = 0.0) -> bool:
        """Reduce stock by qty. Tries IR direct overwrite first, then write-off documents.
        new_absolute_qty: the target quantity to set (used for IR direct overwrite)."""
        clean = str(onec_id).strip("{}")
        from datetime import datetime as _dt
        period = _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        _zero = "00000000-0000-0000-0000-000000000000"
        org_key = await self._get_org_key()
        wh_key = await self._get_warehouse_key()
        summa = round(qty * float(price or 0), 2)

        debit_key, credit_key = await self._get_stock_accounts(clean)

        NO_ACCOUNTING = {
            "ФормироватьПроводки": False,
            "ОтражатьВБухгалтерскомУчете": False,
            "ОтражатьВНалоговомУчете": False,
        }

        import re as _re_ir
        import uuid as _uuid_mod0
        _IR_SKIP = {"Количество", "Стоимость", "Резерв", "odata.metadata", "odata.type", "odata.etag"}
        _GUID_PAT = _re_ir.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', _re_ir.IGNORECASE
        )

        # ── 0. IR direct overwrite (set absolute qty) ──────────────────────────
        ok_irg, ir_data = await self._request(
            "GET",
            f"odata/standard.odata/InformationRegister_ОстаткиТоваров"
            f"?$format=json&$filter=Номенклатура_Key eq guid'{clean}'&$top=1"
        )
        logger.debug(f"1C write-off IR GET: ok={ok_irg} rows={len((ir_data or {}).get('value', []))}")
        if ok_irg and isinstance(ir_data, dict):
            ir_rows = ir_data.get("value", [])
            if ir_rows:
                ir_rec = ir_rows[0]
                key_parts = []
                for k, v in ir_rec.items():
                    if k in _IR_SKIP or "@" in k or k.endswith("_Type"):
                        continue
                    if k.lower() in ("period", "период"):
                        key_parts.append(f"{k}=datetime'{str(v)[:19]}'")
                    elif k.endswith("_Key"):
                        key_parts.append(f"{k}=guid'{str(v).strip('{}')}'")
                    elif _GUID_PAT.match(str(v).strip("{}")):
                        key_parts.append(f"{k}=guid'{str(v).strip('{}')}'")
                        type_val = ir_rec.get(k + "_Type")
                        if type_val:
                            key_parts.append(f"{k}_Type='{type_val}'")
                    else:
                        key_parts.append(f"{k}='{v}'")
                logger.debug(f"1C write-off IR key_parts: {key_parts}")
                logger.debug(f"1C write-off IR rec fields: {list(ir_rec.keys())} nom={ir_rec.get('Номенклатура_Key', 'MISSING')}")
                if key_parts:
                    patch_payload = {
                        "Количество": float(new_absolute_qty),
                        "Стоимость": round(new_absolute_qty * float(price or 0), 2),
                    }
                    ok_put, resp_put = await self._request(
                        "PATCH",
                        f"odata/standard.odata/InformationRegister_ОстаткиТоваров"
                        f"({','.join(p.strip() for p in key_parts)})",
                        json=patch_payload,
                    )
                    logger.debug(f"1C write-off IR PATCH: ok={ok_put} resp={str(resp_put)[:200]}")
                    if ok_put:
                        logger.info(f"1C write-off via IR PATCH: qty={new_absolute_qty} (delta=-{qty})")
                        return True
            # No existing IR record — POST with absolute qty
            ir_post = {
                "Номенклатура_Key": clean,
                "Характеристика_Key": _zero,
                "Количество": float(new_absolute_qty),
                "Стоимость": round(new_absolute_qty * float(price or 0), 2),
            }
            if wh_key:
                ir_post["СтруктурнаяЕдиница"] = wh_key
            ok_irp, resp_irp = await self._request(
                "POST", "odata/standard.odata/InformationRegister_ОстаткиТоваров", json=ir_post
            )
            logger.debug(f"1C write-off IR POST: ok={ok_irp} resp={str(resp_irp)[:100]}")
            if ok_irp:
                logger.info(f"1C write-off via IR POST abs: qty={new_absolute_qty}")
                return True

        # ── 0a. Document_ОприходованиеЗапасов with NEGATIVE quantity ───────────
        # Same document that successfully adds stock; negative qty = write-off movement.
        for neg_tab in ("Запасы", "Товары"):
            for no_acc0 in ([False, True] if debit_key else [True]):
                neg_row: dict = {
                    "LineNumber": 1,
                    "Номенклатура_Key": clean,
                    "Количество": -float(qty),
                    "Цена": float(price or 0),
                    "Сумма": -round(qty * float(price or 0), 2),
                    "Характеристика_Key": _zero,
                }
                if not no_acc0 and debit_key:
                    for fld in ("СчетДт_Key", "СчетУчета_Key", "СчетДебета_Key"):
                        neg_row[fld] = debit_key
                    for fld in ("СчетКт_Key", "СчетКредита_Key"):
                        neg_row[fld] = credit_key or _zero
                neg_hdr: dict = {
                    "Ref_Key": str(_uuid_mod0.uuid4()),
                    "Date": period,
                    "Комментарий": "Авто из 1С Хелпер",
                    neg_tab: [neg_row],
                }
                if org_key:
                    neg_hdr["Организация_Key"] = org_key
                if wh_key:
                    neg_hdr["Склад_Key"] = wh_key
                    neg_hdr["СтруктурнаяЕдиница_Key"] = wh_key
                if not no_acc0 and debit_key:
                    neg_hdr["СчетДт_Key"] = debit_key
                    neg_hdr["СчетКт_Key"] = credit_key or _zero
                if no_acc0:
                    neg_hdr.update(NO_ACCOUNTING)
                ok_nc, resp_nc = await self._request(
                    "POST", "odata/standard.odata/Document_ОприходованиеЗапасов", json=neg_hdr
                )
                if not ok_nc:
                    logger.debug(f"1C ОприходованиеЗапасов-neg POST failed ({neg_tab}): {str(resp_nc)[:200]}")
                    break
                neg_ref = str((resp_nc or {}).get("Ref_Key", "") if isinstance(resp_nc, dict) else "").strip("{}")
                if not neg_ref:
                    break
                ok_np, resp_np = await self._request(
                    "POST", f"odata/standard.odata/Document_ОприходованиеЗапасов(guid'{neg_ref}')/Post", json={}
                )
                if ok_np:
                    logger.info(f"1C write-off via ОприходованиеЗапасов neg-qty ({neg_tab} no_acc={no_acc0}): qty=-{qty}")
                    return True
                logger.debug(f"1C ОприходованиеЗапасов-neg Post failed ({neg_tab} no_acc={no_acc0}): {str(resp_np)[:300]}")
                await self._request(
                    "PATCH", f"odata/standard.odata/Document_ОприходованиеЗапасов(guid'{neg_ref}')",
                    json={"ПометкаУдаления": True}
                )

        # ── 1. Write-off documents (with and without accounting) ─────────────────
        def _make_wo_row(include_acct: bool) -> dict:
            r: dict = {
                "LineNumber": "1",
                "Номенклатура_Key": clean,
                "Количество": float(qty),
                "Цена": float(price or 0),
                "Сумма": summa,
                "Характеристика_Key": _zero,
            }
            if include_acct and debit_key:
                r["СчетДт_Key"] = debit_key
                r["СчетКт_Key"] = credit_key or _zero
            return r

        import uuid as _uuid_mod

        # ── 1a. ИнвентаризацияЗапасов — sets absolute quantity (inventory audit) ──
        for inv_tab in ("ТоварыЗапасы", "Запасы", "Товары"):
            new_ref = str(_uuid_mod.uuid4())
            inv_row: dict = {
                "LineNumber": "1",
                "Номенклатура_Key": clean,
                "КоличествоФакт": float(new_absolute_qty),
                "Количество": float(new_absolute_qty),
                "Характеристика_Key": _zero,
            }
            inv_hdr: dict = {
                "Ref_Key": new_ref,
                "Date": period,
                "Комментарий": "Авто из 1С Хелпер",
                inv_tab: [inv_row],
            }
            if org_key:
                inv_hdr["Организация_Key"] = org_key
            if wh_key:
                inv_hdr["Склад_Key"] = wh_key
                inv_hdr["СтруктурнаяЕдиница_Key"] = wh_key
            # NOTE: do NOT add NO_ACCOUNTING — it suppresses AccumulationRegister movements
            ok_ic, resp_ic = await self._request(
                "POST", "odata/standard.odata/Document_ИнвентаризацияЗапасов", json=inv_hdr
            )
            if not ok_ic:
                logger.debug(f"1C Document_ИнвентаризацияЗапасов POST failed ({inv_tab}): {str(resp_ic)[:200]}")
                if "не найдена" in str(resp_ic):
                    break  # document type not published
                continue
            inv_ref = str((resp_ic or {}).get("Ref_Key", new_ref) if isinstance(resp_ic, dict) else new_ref).strip("{}")
            ok_ip, resp_ip = await self._request(
                "POST", f"odata/standard.odata/Document_ИнвентаризацияЗапасов(guid'{inv_ref}')/Post", json={}
            )
            if ok_ip:
                logger.info(f"1C write-off via ИнвентаризацияЗапасов ({inv_tab}): {inv_ref} abs_qty={new_absolute_qty}")
                return True
            logger.debug(f"1C ИнвентаризацияЗапасов Post failed ({inv_tab}): {str(resp_ip)[:300]}")
            await self._request("PATCH", f"odata/standard.odata/Document_ИнвентаризацияЗапасов(guid'{inv_ref}')",
                                json={"ПометкаУдаления": True})

        # ── 1b. КорректировкаЗапасов — sets absolute quantity (best for adjustments) ──
        for korr_tab in ("Запасы", "Товары"):
            new_ref = str(_uuid_mod.uuid4())
            korr_row: dict = {
                "LineNumber": "1",
                "Номенклатура_Key": clean,
                "КоличествоФакт": float(new_absolute_qty),
                "Количество": float(new_absolute_qty),
                "Характеристика_Key": _zero,
            }
            korr_hdr: dict = {
                "Ref_Key": new_ref,
                "Date": period,
                "Комментарий": "Авто из 1С Хелпер",
                korr_tab: [korr_row],
            }
            if org_key:
                korr_hdr["Организация_Key"] = org_key
            if wh_key:
                korr_hdr["Склад_Key"] = wh_key
                korr_hdr["СтруктурнаяЕдиница_Key"] = wh_key
            korr_hdr.update(NO_ACCOUNTING)
            ok_kc, resp_kc = await self._request(
                "POST", "odata/standard.odata/Document_КорректировкаЗапасов", json=korr_hdr
            )
            if not ok_kc:
                logger.debug(f"1C Document_КорректировкаЗапасов POST failed ({korr_tab}): {str(resp_kc)[:200]}")
                break
            korr_ref = str((resp_kc or {}).get("Ref_Key", new_ref) if isinstance(resp_kc, dict) else new_ref).strip("{}")
            ok_kp, resp_kp = await self._request(
                "POST", f"odata/standard.odata/Document_КорректировкаЗапасов(guid'{korr_ref}')/Post", json={}
            )
            if ok_kp:
                logger.info(f"1C write-off via КорректировкаЗапасов: {korr_ref} abs_qty={new_absolute_qty}")
                return True
            logger.debug(f"1C КорректировкаЗапасов Post failed: {str(resp_kp)[:300]}")
            await self._request("PATCH", f"odata/standard.odata/Document_КорректировкаЗапасов(guid'{korr_ref}')",
                                json={"ПометкаУдаления": True})

        for doc_name, tab_name in [("Document_СписаниеЗапасов", "Запасы"),
                                    ("Document_СписаниеТоваров", "Товары")]:
            for no_acc in ([False, True] if debit_key else [True]):
                new_ref = str(_uuid_mod.uuid4())
                header: dict = {
                    "Ref_Key": new_ref,
                    "Date": period,
                    "Комментарий": "Авто из 1С Хелпер",
                    tab_name: [_make_wo_row(not no_acc)],
                }
                if org_key:
                    header["Организация_Key"] = org_key
                if wh_key:
                    header["Склад_Key"] = wh_key
                    header["СтруктурнаяЕдиница_Key"] = wh_key
                if not no_acc and debit_key:
                    header["СчетДт_Key"] = debit_key
                    header["СчетКт_Key"] = credit_key or _zero
                if no_acc:
                    header.update(NO_ACCOUNTING)

                ok_c, resp_c = await self._request(
                    "POST", f"odata/standard.odata/{doc_name}", json=header
                )
                if not ok_c:
                    logger.debug(f"1C {doc_name} POST failed: {str(resp_c)[:300]}")
                    break  # doc type not available
                doc_ref_created = (resp_c or {}).get("Ref_Key", new_ref) if isinstance(resp_c, dict) else new_ref
                clean_ref = str(doc_ref_created).strip("{}")

                # GET back document — inspect auto-filled fields
                ok_g, doc_data = await self._request(
                    "GET", f"odata/standard.odata/{doc_name}(guid'{clean_ref}')?$format=json"
                )
                if ok_g and isinstance(doc_data, dict):
                    doc_fields = {k: v for k, v in doc_data.items() if "Счет" in k or "Статус" in k or "Вид" in k}
                    logger.debug(f"1C {doc_name} auto-fields: {doc_fields}")

                ok_p, resp_p = await self._request(
                    "POST", f"odata/standard.odata/{doc_name}(guid'{clean_ref}')/Post", json={},
                )
                if ok_p:
                    logger.info(f"1C write-off posted ({doc_name}{'  без проводок' if no_acc else ''}): {clean_ref} qty={qty}")
                    return True
                logger.warning(f"1C {doc_name} Post failed (no_acc={no_acc}): {str(resp_p)[:400]}")
                await self._request("PATCH", f"odata/standard.odata/{doc_name}(guid'{clean_ref}')",
                                    json={"ПометкаУдаления": True})

        # ── 2. AccumulationRegister Расход movement ─────────────────────────────
        for reg in ("AccumulationRegister_ЗапасыНаСкладах", "AccumulationRegister_ТоварыНаСкладах"):
            payload: dict = {
                "Номенклатура_Key": clean,
                "Характеристика_Key": _zero,
                "Количество": float(qty),
                "Стоимость": summa,
                "ВидДвижения": "Расход",
                "RecordType": "Expense",
            }
            if wh_key:
                payload["СтруктурнаяЕдиница_Key"] = wh_key
            ok_r, _ = await self._request("POST", f"odata/standard.odata/{reg}", json=payload)
            if ok_r:
                logger.info(f"1C write-off via {reg}: qty={qty}")
                return True
        return False

    async def _get_product_stock_qty(self, onec_id: str) -> float:
        """Return current stock quantity for a single product from 1C (0 if not found)."""
        clean = str(onec_id).strip("{}")
        sources = [
            (f"odata/standard.odata/InformationRegister_ОстаткиТоваров"
             f"?$format=json&$filter=Номенклатура_Key eq guid'{clean}'&$top=10&$select=Количество",
             "Количество"),
            (f"odata/standard.odata/AccumulationRegister_ЗапасыНаСкладах/Balance"
             f"?$format=json&$filter=Номенклатура_Key eq guid'{clean}'&$top=1",
             "КоличествоБаланс"),
            (f"odata/standard.odata/AccumulationRegister_ТоварыНаСкладах/Balance"
             f"?$format=json&$filter=Номенклатура_Key eq guid'{clean}'&$top=1",
             "КоличествоБаланс"),
        ]
        for path, qty_field in sources:
            ok, data = await self._request("GET", path)
            if ok and isinstance(data, dict):
                total = sum(float(r.get(qty_field) or 0) for r in data.get("value", []))
                if total > 0:
                    logger.debug(f"1C _get_product_stock_qty source={path[:80]} qty={total}")
                    return total
        return 0.0

    async def set_stock(self, onec_id: str, quantity: float, price: float = 0.0,
                         use_accounting: bool = True, replace: bool = False) -> bool:
        """Post initial stock quantity to 1C.

        replace=True         → compute delta vs current balance; post only the difference
        use_accounting=True  → try with debit/credit accounts first, fallback to no-accounting
        use_accounting=False → skip accounting journal entirely (ФормироватьПроводки=false)

        Strategy (first success wins):
        1. Direct write to AccumulationRegister (Запасы / ТоварыНаСкладах / ТоварыОрг)
        2. Document_ОприходованиеЗапасов with / without accounting
        3. Document_ОприходованиеТоваров / Document_ПоступлениеТоваровУслуг fallback
        Unposted documents are kept as drafts (not deleted) so user can post manually.
        """
        if quantity is None or quantity < 0:
            return False

        quantity = round(float(quantity), 3)  # clean float before any arithmetic
        abs_qty = quantity  # absolute target — used for IR PATCH later

        # ── replace mode: compute delta vs current 1C balance ──────────────────────
        if replace:
            current_qty = round(await self._get_product_stock_qty(onec_id), 3)
            delta = round(quantity - current_qty, 3)
            logger.info(f"1C set_stock replace: onec_id={onec_id} "
                        f"new={quantity} current={current_qty} delta={delta}")
            if abs(delta) < 0.001:
                return True  # already correct, nothing to post
            if delta < 0:
                # Write-off: try Document_СписаниеЗапасов / AccumulationRegister Расход
                written_off = await self._write_off_stock(
                    onec_id, abs(delta), price, use_accounting,
                    new_absolute_qty=quantity,
                )
                if written_off:
                    return True
                # Write-off failed — do NOT fall through to receipt document (would add stock)
                logger.warning(
                    f"1C write-off failed for onec_id={onec_id} delta={delta}: "
                    f"stock NOT changed in 1C"
                )
                return False
            else:
                quantity = delta  # post only the positive delta as receipt

        if not quantity or quantity <= 0:
            return False
        onec_id = str(onec_id).strip("{}")
        from datetime import datetime as _dt
        period = _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        _zero = "00000000-0000-0000-0000-000000000000"

        org_key = await self._get_org_key()
        wh_key = await self._get_warehouse_key()
        summa = round(float(quantity) * float(price or 0), 2)
        ir_ok = False  # tracks if InformationRegister write succeeded (partial success)

        # ── 0. Direct InformationRegister_ОстаткиТоваров write ──
        # Confirmed published in OData. Try PUT on existing record or POST new one.
        if not getattr(self, "_ir_stock_schema", None):
            # Learn schema from any existing record in this register
            ok_s, schema_data = await self._request(
                "GET", "odata/standard.odata/InformationRegister_ОстаткиТоваров?$format=json&$top=1"
            )
            if ok_s and isinstance(schema_data, dict) and schema_data.get("value"):
                self._ir_stock_schema = schema_data["value"][0]
                logger.info(f"1C InformationRegister_ОстаткиТоваров schema: {list(self._ir_stock_schema.keys())}")
            else:
                self._ir_stock_schema = {}
        schema = getattr(self, "_ir_stock_schema", {})

        # Try GET specific product record (for PUT), fall back to POST
        ok_ir_get, ir_existing = await self._request(
            "GET",
            f"odata/standard.odata/InformationRegister_ОстаткиТоваров"
            f"?$format=json&$filter=Номенклатура_Key eq guid'{onec_id}'&$top=1"
        )
        ir_rec = ((ir_existing or {}).get("value") or [{}])[0] if (ok_ir_get and ir_existing) else {}

        def _build_ir_payload(template: dict) -> dict:
            """Build IR payload: keep _Type fields (needed for composite refs), drop nav-links."""
            payload = {}
            for k, v in template.items():
                # Skip navigation link fields (contain @) and pure metadata
                if "@" in k:
                    continue
                if k in ("Количество", "Резерв", "Стоимость",
                         "odata.metadata", "odata.type", "odata.etag"):
                    continue
                payload[k] = v
            payload["Номенклатура_Key"] = onec_id
            payload["Количество"] = float(quantity)
            return payload

        if ir_rec:  # existing record → build PUT URL + PUT
            import re as _re2
            _IR_SKIP = {"Количество", "Стоимость", "Резерв", "odata.metadata", "odata.type", "odata.etag"}
            _GUID_PAT = _re2.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', _re2.IGNORECASE)
            key_parts = []
            for k, v in ir_rec.items():
                if k in _IR_SKIP or "@" in k or k.endswith("_Type"):
                    continue
                if k.lower() in ("period", "период"):
                    key_parts.append(f"{k}=datetime'{str(v)[:19]}'")
                elif k.endswith("_Key"):
                    key_parts.append(f"{k}=guid'{str(v).strip('{}')}' ")
                elif _GUID_PAT.match(str(v).strip("{}")):
                    key_parts.append(f"{k}=guid'{str(v).strip('{}')}'")
                    type_val = ir_rec.get(k + "_Type")
                    if type_val:
                        key_parts.append(f"{k}_Type='{type_val}'")
                else:
                    key_parts.append(f"{k}='{v}'")

            if key_parts:
                ok_put, resp_put = await self._request(
                    "PATCH",
                    f"odata/standard.odata/InformationRegister_ОстаткиТоваров({','.join(p.strip() for p in key_parts)})",
                    json={"Количество": float(abs_qty), "Стоимость": round(abs_qty * float(price or 0), 2)}
                )
                if ok_put:
                    logger.info(f"1C stock set via PATCH InformationRegister_ОстаткиТоваров: {onec_id} qty={quantity}")
                    ir_ok = True
                    # Don't return yet — also try document posting for full 1C AR update
                else:
                    logger.warning(f"1C InformationRegister_ОстаткиТоваров PATCH failed: {str(resp_put)[:200]}")

        # No existing record OR PUT failed → try POST (create new record)
        # Use template if available; fall back to minimal payload when register is empty
        ir_template = ir_rec or schema  # may be {} (falsy) for a fresh/empty register
        ir_payload = _build_ir_payload(ir_template) if ir_template else {
            "Номенклатура_Key": onec_id,
            "Характеристика_Key": _zero,
            "Количество": float(quantity),
            "Стоимость": summa,
        }
        # Optionally add warehouse key for УНФ-style registers
        if wh_key:
            ir_payload.setdefault("СтруктурнаяЕдиница_Key", wh_key)
        logger.info(f"1C InformationRegister_ОстаткиТоваров POST payload keys: {list(ir_payload.keys())}")
        try:
            ok_post, resp_post = await self._request(
                "POST", "odata/standard.odata/InformationRegister_ОстаткиТоваров",
                json=ir_payload
            )
            logger.info(f"1C InformationRegister_ОстаткиТоваров POST result: ok={ok_post} resp={str(resp_post)[:150]}")
            if ok_post:
                logger.info(f"1C stock set via POST InformationRegister_ОстаткиТоваров: {onec_id} qty={quantity}")
                ir_ok = True
                # Don't return yet — also try document posting for full 1C AR update
        except Exception as _e:
            logger.warning(f"1C InformationRegister_ОстаткиТоваров POST exception: {_e}")

        # ── 1. Direct AccumulationRegister write (no document, no account required) ──
        # Try both English (RecordType) and Russian (ВидДвижения) field name conventions
        base_reg = {
            "Номенклатура_Key": onec_id,
            "Количество": float(quantity),
            "Стоимость": summa,
            "Характеристика_Key": _zero,
        }
        # УНФ-specific: warehouse field name differs per register
        base_unf = {**base_reg}
        if wh_key:
            base_unf["СтруктурнаяЕдиница_Key"] = wh_key  # ЗапасыНаСкладах uses this
        if org_key:
            base_unf["Организация_Key"] = org_key

        base_std = {**base_reg}
        if wh_key:
            base_std["Склад_Key"] = wh_key                # УТ/КА registers use Склад_Key
        if org_key:
            base_std["Организация_Key"] = org_key

        # GET a sample record to learn actual field names (once per client instance)
        if not getattr(self, "_reg_fields_logged", False):
            self._reg_fields_logged = True
            for _reg in ("AccumulationRegister_ЗапасыНаСкладах", "AccumulationRegister_Запасы"):
                ok_g, gs = await self._request(
                    "GET", f"odata/standard.odata/{_reg}?$format=json&$top=1"
                )
                if ok_g and isinstance(gs, dict) and gs.get("value"):
                    logger.info(f"1C {_reg} sample fields: {list(gs['value'][0].keys())}")
                    break
                logger.info(f"1C {_reg} GET: ok={ok_g} data={str(gs)[:120]}")

        # Discover published AccumulationRegister entities once per client instance
        if not getattr(self, "_published_acc_registers", None):
            ok0, root = await self._request("GET", "odata/standard.odata/?$format=json")
            if ok0 and isinstance(root, dict):
                all_names = {e.get("name", "") for e in root.get("value", [])}
                self._published_acc_registers = {
                    n for n in all_names if n.startswith("AccumulationRegister_")
                }
                self._published_info_registers = {
                    n for n in all_names if n.startswith("InformationRegister_")
                }
                self._published_acc_registers2 = {
                    n for n in all_names if n.startswith("AccountingRegister_")
                }
                logger.info(f"1C published AccumulationRegisters: {sorted(self._published_acc_registers)}")
                logger.info(f"1C published InformationRegisters: {sorted(self._published_info_registers)}")
                logger.info(f"1C published AccountingRegisters: {sorted(self._published_acc_registers2)}")
            else:
                self._published_acc_registers = set()
                self._published_info_registers = set()
                self._published_acc_registers2 = set()
        pub_regs = getattr(self, "_published_acc_registers", set())

        register_candidates = [
            # УНФ-specific registers (warehouse = СтруктурнаяЕдиница_Key)
            # Try both main endpoint and _RecordType endpoint
            ("AccumulationRegister_ЗапасыНаСкладах",           {"Period": period, "RecordType": "Receipt", **base_unf}),
            ("AccumulationRegister_ЗапасыНаСкладах",           {"Period": period, "ВидДвижения": "Приход", **base_unf}),
            ("AccumulationRegister_ЗапасыНаСкладах_RecordType",  {"Period": period, "RecordType": "Receipt", **base_unf}),
            ("AccumulationRegister_ЗапасыНаСкладах_RecordType",  {"Period": period, "ВидДвижения": "Приход", **base_unf}),
            ("AccumulationRegister_Запасы",                    {"Period": period, "RecordType": "Receipt", **base_unf}),
            ("AccumulationRegister_Запасы",                    {"Period": period, "ВидДвижения": "Приход", **base_unf}),
            ("AccumulationRegister_Запасы_RecordType",         {"Period": period, "RecordType": "Receipt", **base_unf}),
            ("AccumulationRegister_Запасы_RecordType",         {"Period": period, "ВидДвижения": "Приход", **base_unf}),
            # УТ/КА registers (warehouse = Склад_Key)
            ("AccumulationRegister_ТоварыНаСкладах", {"Period": period, "RecordType": "Receipt", **base_std}),
            ("AccumulationRegister_ТоварыОрганизаций",{"Period": period, "RecordType": "Receipt", **base_std}),
        ]
        for acc_reg, rec_payload in register_candidates:

            # Skip registers not published in this 1С instance
            if pub_regs and acc_reg not in pub_regs:
                logger.debug(f"1C skip unpublished {acc_reg}")
                continue
            ok, resp = await self._request(
                "POST", f"odata/standard.odata/{acc_reg}",
                json=rec_payload
            )
            if ok:
                logger.info(f"1C stock set (direct {acc_reg}): {onec_id} qty={quantity}")
                return True
            err_code = (resp or {}).get("status", "?")
            err_msg  = str((resp or {}).get("error", ""))[:500]
            logger.warning(f"1C {acc_reg} POST failed [{err_code}]: {err_msg}")
        logger.warning("1C stock: all direct register writes failed — falling back to document")

        # ── 2-4. Document-based approaches ──
        debit_key, credit_key = await self._get_stock_accounts(onec_id)

        # If the product has no СчетУчетаЗапасов_Key set, patch it so the posting handler
        # can read the account from the product card (that's where 1C reads it from).
        if debit_key and not getattr(self, f"_nom_patched_{onec_id}", False):
            ok_p, resp_p = await self._request(
                "PATCH",
                f"odata/standard.odata/Catalog_Номенклатура(guid'{onec_id}')",
                json={"СчетУчетаЗапасов_Key": debit_key}
            )
            logger.info(f"1C PATCH Номенклатура СчетУчетаЗапасов_Key={debit_key}: ok={ok_p} resp={str(resp_p)[:120]}")
            if ok_p:
                setattr(self, f"_nom_patched_{onec_id}", True)

        def _make_row(with_account: bool) -> dict:
            r: dict = {
                "LineNumber": 1,
                "Номенклатура_Key": onec_id,
                "Количество": float(quantity),
                "Цена": float(price or 0),
                "Сумма": summa,
                "Характеристика_Key": _zero,
            }
            if with_account:
                # All possible debit account field name variants in 1C OData
                for f in ("СчетДт_Key", "СчетУчета_Key", "СчетДебета_Key"):
                    r[f] = debit_key or _zero
                # Credit account
                for f in ("СчетКт_Key", "СчетКредита_Key"):
                    r[f] = credit_key or _zero
            return r

        # Flags that tell 1C to skip bookkeeping journal (only stock movements matter)
        NO_ACCOUNTING = {
            "ФормироватьПроводки": False,
            "ОтражатьВБухгалтерскомУчете": False,
            "ОтражатьВНалоговомУчете": False,
        }

        doc_variants = [
            # (doc_type, tab_section, extra_fields)
            # Inventory adjustment — may not require accounting accounts
            ("Document_КорректировкаЗапасов",       "Запасы", {}),
            ("Document_ИнвентаризацияТоваров",     "Товары", {}),  # inventory count
            # Standard receipt
            ("Document_ОприходованиеЗапасов",   "Запасы", {}),
            ("Document_ОприходованиеЗапасов",   "Запасы", {"ВидОперации": "НачальныеОстатки"}),
            ("Document_ВводОстатков",            "Запасы", {}),
            ("Document_ВводОстатков",            "Товары", {}),
            ("Document_ОприходованиеТоваров",    "Товары", {}),
            ("Document_ПоступлениеТоваровУслуг", "Товары", {}),
        ]
        # Respect use_accounting setting: with accounts first if enabled, then without
        acct_attempts = ([False, True] if use_accounting else [True])

        for doc_type, tab_name, extra_fields in doc_variants:

            def _build_doc(no_accounting: bool, _tab=tab_name, _extra=extra_fields) -> dict:
                d: dict = {
                    "Date": period,
                    "Комментарий": "Авто из 1С Хелпер",
                    _tab: [_make_row(not no_accounting)],
                }
                if org_key:
                    d["Организация_Key"] = org_key
                if wh_key:
                    d["Склад_Key"] = wh_key
                    d["СтруктурнаяЕдиница_Key"] = wh_key  # УНФ field name
                if not no_accounting and debit_key:
                    d["СчетДт_Key"] = debit_key
                    d["СчетКт_Key"] = credit_key or _zero
                if no_accounting:
                    d.update(NO_ACCOUNTING)
                d.update(_extra)
                return d

            doc_created = False
            for no_acc in acct_attempts:
                doc = _build_doc(no_acc)
                ok, resp = await self._request(
                    "POST", f"odata/standard.odata/{doc_type}", json=doc
                )
                if not (ok and isinstance(resp, dict) and resp.get("Ref_Key")):
                    logger.warning(f"1C stock create failed ({doc_type}): {resp}")
                    break  # doc type not available — skip remaining attempts for this type

                doc_created = True
                ref_key = str(resp["Ref_Key"]).strip("{}")

                # ── GET back the created doc header (no $expand — УНФ returns 501 for tabular) ──
                ok_g, doc_data = await self._request(
                    "GET",
                    f"odata/standard.odata/{doc_type}(guid'{ref_key}')?$format=json"
                )
                if ok_g and isinstance(doc_data, dict):
                    hdr_acct_fields = [k for k in doc_data if "Счет" in k or "Провод" in k]
                    logger.info(f"1C {doc_type} header acct fields: {hdr_acct_fields}")
                    for af in ("СчетДт_Key", "СчетУчета_Key", "СчетДебета_Key"):
                        auto_v = str(doc_data.get(af, "")).strip("{}")
                        if auto_v and auto_v != _zero and not debit_key:
                            debit_key = auto_v
                            logger.info(f"1C auto-filled {af}={debit_key} in {doc_type} header")
                            break

                ok2, resp2 = await self._request(
                    "POST",
                    f"odata/standard.odata/{doc_type}(guid'{ref_key}')/Post"
                )
                if ok2:
                    suffix = " (без проводок)" if no_acc else ""
                    logger.info(f"1C stock posted ({doc_type}){suffix}: {onec_id} qty={quantity}")
                    return True
                # 1C sometimes returns HTTP 500 even when the document was actually posted.
                # Verify by reading back the document state.
                ok_v, doc_v = await self._request(
                    "GET",
                    f"odata/standard.odata/{doc_type}(guid'{ref_key}')?$format=json"
                )
                проведен = doc_v.get("Проведен") if isinstance(doc_v, dict) else None
                logger.info(f"1C verify GET: ok={ok_v} Проведен={проведен} keys={list(doc_v.keys())[:8] if isinstance(doc_v, dict) else '?'}")
                if ok_v and проведен:
                    logger.info(f"1C stock posted (verified after 500) ({doc_type}): {onec_id} qty={quantity}")
                    return True
                logger.warning(f"1C stock Post failed ({doc_type} no_acc={no_acc}): {resp2}")
                logger.info(f"1C stock draft saved ({doc_type} guid={ref_key}) — marking for deletion, retrying without accounting")
                # Mark failed draft for deletion, then retry with next acct_attempt (no-accounting mode)
                await self._request(
                    "PATCH",
                    f"odata/standard.odata/{doc_type}(guid'{ref_key}')",
                    json={"ПометкаУдаления": True},
                )
                doc_created = False  # allow next attempt to try a fresh document
                continue  # try next no_acc value (e.g. True = without accounting)
            if doc_created:
                break  # stop trying other doc types after first draft

        if ir_ok:
            logger.warning(f"1C set_stock: document post failed but IR updated for {onec_id} — bot display ok, 1С AR not updated (write-off may fail in 1С)")
            return True
        logger.warning(f"1C set_stock: all attempts failed for {onec_id} qty={quantity}")
        return False

    async def create_barcode(self, onec_id: str, barcode: str) -> bool:
        """Create a barcode record in 1C.

        Handles two fundamentally different 1C structures:
        1. Catalog_ШтрихкодыНоменклатуры  — uses Владелец_Key + Владелец_Type
        2. InformationRegister_ШтрихкодыНоменклатуры — uses Номенклатура_Key (dimension key)
        """
        onec_id = str(onec_id).strip("{}")  # normalize GUID format
        bc_type = self._detect_barcode_type(barcode)
        _zero = "00000000-0000-0000-0000-000000000000"
        owner_type = "StandardODATA.Catalog_Номенклатура"

        # ── 1. PATCH Catalog_Номенклатура with direct Штрихкод field (реальное поле на сущности)
        patch_ok = False
        ok, resp = await self._request(
            "PATCH", f"odata/standard.odata/Catalog_Номенклатура(guid'{onec_id}')",
            json={"Штрихкод": barcode}
        )
        if ok:
            logger.info(f"1C barcode set (PATCH Catalog/Штрихкод): {barcode} → {onec_id}")
            patch_ok = True
        else:
            logger.warning(f"1C barcode PATCH Catalog/Штрихкод failed: {resp}")

        # ── 2. ALWAYS also POST to InformationRegister so barcode appears in Штрихкоды tab
        unit_key = _zero
        ok_u, prod = await self._request(
            "GET", f"odata/standard.odata/Catalog_Номенклатура(guid'{onec_id}')?$format=json"
        )
        if ok_u and isinstance(prod, dict):
            unit_key = str(prod.get("ЕдиницаХранения_Key") or _zero).strip("{}")
        ok, resp = await self._request(
            "POST", "odata/standard.odata/InformationRegister_ШтрихкодыНоменклатуры",
            json={"Номенклатура_Key": onec_id, "Штрихкод": barcode, "ТипШтрихкода": bc_type,
                  "Характеристика_Key": _zero, "Партия_Key": _zero, "ЕдиницаИзмерения_Key": unit_key}
        )
        if ok:
            logger.info(f"1C barcode set (POST InformationRegister): {barcode} → {onec_id}")
            return True
        if isinstance(resp, dict) and resp.get("status") == 400:
            logger.info(f"1C barcode register already has {barcode} — treating as OK")
            return True
        logger.warning(f"1C barcode POST InformationRegister failed: {resp}")
        put_key = (f"Номенклатура_Key=guid'{onec_id}',"
                   f"Штрихкод='{barcode}',"
                   f"Характеристика_Key=guid'{_zero}',"
                   f"Партия_Key=guid'{_zero}',"
                   f"ЕдиницаИзмерения_Key=guid'{unit_key}'")
        ok, resp = await self._request(
            "PUT",
            f"odata/standard.odata/InformationRegister_ШтрихкодыНоменклатуры({put_key})",
            json={"Номенклатура_Key": onec_id, "Штрихкод": barcode,
                 "ТипШтрихкода": bc_type, "Характеристика_Key": _zero,
                 "Партия_Key": _zero, "ЕдиницаИзмерения_Key": unit_key}
        )
        if ok:
            logger.info(f"1C barcode set (PUT InformationRegister): {barcode} → {onec_id}")
            return True
        logger.warning(f"1C barcode PUT InformationRegister failed: {resp}")

        logger.warning(f"1C barcode create FAILED for barcode={barcode} onec_id={onec_id}")
        return False

    async def probe_barcode_price(self, onec_id: str, test_barcode: str = "4607141232117", test_price: float = 100.0) -> dict:
        """Diagnostic: try all barcode/price write variants, return full 1C error details."""
        from datetime import datetime as _dt
        period = _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        bc_type = self._detect_barcode_type(test_barcode)
        _zero = "00000000-0000-0000-0000-000000000000"
        onec_id = str(onec_id).strip("{}")

        price_types = await self.get_price_types()
        price_type_key = await self._get_or_fetch_price_type_key()

        # ── GET existing records to discover real field structure
        existing_bc, existing_price = {}, {}
        for entity in ("InformationRegister_ШтрихкодыНоменклатуры",):
            ok, data = await self._request("GET", f"odata/standard.odata/{entity}?$format=json&$top=1")
            if ok and isinstance(data, dict) and data.get("value"):
                existing_bc = {k: type(v).__name__ for k, v in data["value"][0].items()
                               if not k.startswith("odata")}
        for entity in ("InformationRegister_ЦеныНоменклатуры",):
            ok, data = await self._request("GET", f"odata/standard.odata/{entity}?$format=json&$top=1")
            if ok and isinstance(data, dict) and data.get("value"):
                existing_price = {k: type(v).__name__ for k, v in data["value"][0].items()
                                  if not k.startswith("odata")}

        # ── GET Catalog_Организации — needed for Document_УстановкаЦенНоменклатуры
        org_key = None
        ok, data = await self._request("GET", "odata/standard.odata/Catalog_Организации?$format=json&$top=1")
        if ok and isinstance(data, dict) and data.get("value"):
            org_key = str(data["value"][0].get("Ref_Key", "")).strip("{}")

        # ── GET Catalog_Валюты — currency needed for Document
        currency_key = None
        ok, data = await self._request("GET", "odata/standard.odata/Catalog_Валюты?$format=json&$top=1")
        if ok and isinstance(data, dict) and data.get("value"):
            currency_key = str(data["value"][0].get("Ref_Key", "")).strip("{}")

        # ── GET product's unit of measure + nom_fields from Catalog_Номенклатура
        unit_key = None
        nom_fields = []
        ok_nom, nom_data = await self._request(
            "GET", f"odata/standard.odata/Catalog_Номенклатура(guid'{onec_id}')?$format=json"
        )
        if ok_nom and isinstance(nom_data, dict):
            unit_key = str(nom_data.get("ЕдиницаХранения_Key") or nom_data.get("ЕдИзм_Key") or "").strip("{}")
            nom_fields = [k for k in nom_data.keys() if not k.startswith("odata") and
                          any(s in k.lower() for s in ("цен", "price", "штрих", "barcode"))]

        # ── GET existing barcodes for this specific product
        existing_bc_for_product = []
        ok, data = await self._request(
            "GET", f"odata/standard.odata/InformationRegister_ШтрихкодыНоменклатуры"
                   f"?$format=json&$filter=Номенклатура_Key eq guid'{onec_id}'&$top=5"
        )
        if ok and isinstance(data, dict):
            existing_bc_for_product = [
                {k: v for k, v in r.items() if not k.startswith("odata")}
                for r in data.get("value", [])
            ]

        # ── GET published entities list (filter barcode/price related)
        published_entities = []
        ok, data = await self._request("GET", "odata/standard.odata/?$format=json")
        if ok and isinstance(data, dict):
            all_ent = [e.get("name", "") for e in data.get("value", [])]
            published_entities = [e for e in all_ent if any(
                s in e for s in ("Штрих", "Barcode", "Цен", "Price", "Установка"))]

        bc_results = []
        # ── PATCH Catalog_Номенклатура with direct Штрихкод field (real field on entity)
        ok, resp = await self._request(
            "PATCH", f"odata/standard.odata/Catalog_Номенклатура(guid'{onec_id}')",
            json={"Штрихкод": test_barcode}
        )
        bc_results.append({"entity": "PATCH Catalog_Ном/Штрихкод (real field)",
                           "ok": ok, "resp": str(resp)[:400]})
        # ── POST InformationRegister with ALL 5 dimension keys in body
        probe_unit = unit_key or _zero
        ok, resp = await self._request(
            "POST", "odata/standard.odata/InformationRegister_ШтрихкодыНоменклатуры",
            json={"Номенклатура_Key": onec_id, "Штрихкод": test_barcode, "ТипШтрихкода": bc_type,
                  "Характеристика_Key": _zero, "Партия_Key": _zero, "ЕдиницаИзмерения_Key": probe_unit}
        )
        bc_results.append({"entity": "InformationRegister_ШтрихкодыНоменклатуры [POST 5-keys]",
                           "ok": ok, "resp": str(resp)[:400]})
        put_key3 = (f"Номенклатура_Key=guid'{onec_id}',"
                    f"Штрихкод='{test_barcode}',"
                    f"Характеристика_Key=guid'{_zero}',"
                    f"Партия_Key=guid'{_zero}',"
                    f"ЕдиницаИзмерения_Key=guid'{probe_unit}'")
        ok, resp = await self._request(
            "PUT",
            f"odata/standard.odata/InformationRegister_ШтрихкодыНоменклатуры({put_key3})",
            json={"Номенклатура_Key": onec_id, "Штрихкод": test_barcode,
                 "ТипШтрихкода": bc_type, "Характеристика_Key": _zero,
                 "Партия_Key": _zero, "ЕдиницаИзмерения_Key": probe_unit}
        )
        bc_results.append({"entity": "InformationRegister_ШтрихкодыНоменклатуры [PUT full 5-key]",
                           "ok": ok, "resp": str(resp)[:600]})

        price_results = []
        vid = price_type_key or _zero
        period0 = "0001-01-01T00:00:00"

        # ── InformationRegister POST
        ok, resp = await self._request(
            "POST", "odata/standard.odata/InformationRegister_ЦеныНоменклатуры",
            json={"Период": period, "Номенклатура_Key": onec_id, "Цена": test_price,
                  "ВидЦены_Key": vid, "Характеристика_Key": _zero, "Упаковка_Key": _zero}
        )
        price_results.append({"register": "InformationRegister_ЦеныНоменклатуры [POST]",
                               "ok": ok, "resp": str(resp)[:600]})

        # ── PUT with composite key in URL
        put_url = (f"odata/standard.odata/InformationRegister_ЦеныНоменклатуры("
                   f"Период=datetime'{period0}',"
                   f"Номенклатура_Key=guid'{onec_id}',"
                   f"ВидЦены_Key=guid'{vid}',"
                   f"Характеристика_Key=guid'{_zero}',Упаковка_Key=guid'{_zero}')")
        ok, resp = await self._request("PUT", put_url,
                                       json={"Цена": test_price, "Номенклатура_Key": onec_id,
                                             "ВидЦены_Key": vid, "Период": period0,
                                             "Характеристика_Key": _zero, "Упаковка_Key": _zero})
        price_results.append({"register": "InformationRegister_ЦеныНоменклатуры [PUT composite]",
                               "ok": ok, "resp": str(resp)[:600]})

        # ── GET existing Document to see its required fields
        existing_doc_fields = {}
        ok, data = await self._request(
            "GET", "odata/standard.odata/Document_УстановкаЦенНоменклатуры?$format=json&$top=1"
        )
        if ok and isinstance(data, dict) and data.get("value"):
            existing_doc_fields = {k: type(v).__name__
                                   for k, v in data["value"][0].items()
                                   if not k.startswith("odata")}

        # ── Document POST with Запасы tabular section (correct name!)
        row_base = {"LineNumber": 1, "Номенклатура_Key": onec_id, "Цена": test_price,
                    "Характеристика_Key": _zero, "ВидЦены_Key": vid}
        if unit_key:
            row_base["Единица_Key"] = unit_key
        doc_base = {"Date": period, "Posted": True, "ВидЦены_Key": vid,
                    "Запасы": [row_base],
                    "ЗаписыватьНовыеЦеныПоверхУстановленных": True}
        if org_key:
            doc_base["Организация_Key"] = org_key
        ok, resp = await self._request("POST", "odata/standard.odata/Document_УстановкаЦенНоменклатуры", json=doc_base)
        price_results.append({"register": "Document_УстановкаЦенНоменклатуры [Запасы+org]",
                               "ok": ok, "resp": str(resp)[:400]})
        # ── Conduct/Post the document (two-step: create then post)
        if ok and isinstance(resp, dict):
            ref_key = str(resp.get("Ref_Key", "")).strip("{}")
            if ref_key:
                ok_p, resp_p = await self._request(
                    "POST",
                    f"odata/standard.odata/Document_УстановкаЦенНоменклатуры(guid'{ref_key}')/Post"
                )
                price_results.append({"register": f"Document (guid'{ref_key[:8]}...')/Post",
                                      "ok": ok_p, "resp": str(resp_p)[:400]})
                if ok_p:
                    await self._request(
                        "PATCH",
                        f"odata/standard.odata/Document_УстановкаЦенНоменклатуры(guid'{ref_key}')",
                        json={"ПометкаУдаления": True}
                    )

        return {
            "onec_id": onec_id,
            "org_key": org_key,
            "published_bc_price_entities": published_entities,
            "price_types_found": [t.get("Description") for t in price_types],
            "price_type_key": price_type_key,
            "nom_price_barcode_fields": nom_fields,
            "existing_barcode_fields": existing_bc,
            "existing_price_fields": existing_price,
            "existing_bc_for_product": existing_bc_for_product,
            "existing_doc_fields": existing_doc_fields,
            "barcode_attempts": bc_results,
            "price_attempts": price_results,
        }

    async def create_receipt(
        self, products: List[dict], supplier: str = "Поставщик"
    ) -> Tuple[bool, Optional[dict]]:
        """Create goods receipt document in 1C."""
        lines = []
        for i, p in enumerate(products, 1):
            lines.append({
                "НомерСтроки": i,
                "Номенклатура_Key": p.get("onec_id"),
                "Количество": p.get("quantity", 1),
                "Цена": p.get("price", 0),
                "Сумма": p.get("quantity", 1) * p.get("price", 0),
            })

        payload = {
            "Дата": datetime.utcnow().isoformat(),
            "Контрагент_Key": supplier,
            "Товары": lines,
        }
        success, data = await self._request(
            "POST",
            "odata/standard.odata/Document_ПоступлениеТоваровУслуг",
            json=payload,
        )
        return success, data

    async def get_edo_documents(self) -> Tuple[bool, List[dict]]:
        """Fetch incoming EDO documents from 1C that may need attention."""
        candidates = [
            "Document_ЭлектронныйДокументВходящий",
            "Document_ЭДОВходящийДокумент",
            "Document_СчетФактураПолученный",
            "Document_ПоступлениеТоваровУслуг",
        ]
        for entity in candidates:
            path = (
                f"odata/standard.odata/{entity}"
                f"?$format=json&$top=20&$orderby=Date desc"
                f"&$select=Ref_Key,Number,Date,СостояниеЭДО,Статус,СтатусЭДО,"
                f"СуммаДокумента,Сумма,Контрагент_Key,ВидОперации"
            )
            success, data = await self._request("GET", path)
            if not success:
                continue
            items = data.get("value", []) if isinstance(data, dict) else []
            if not items:
                continue
            docs = []
            for item in items:
                status = (
                    item.get("СостояниеЭДО") or
                    item.get("СтатусЭДО") or
                    item.get("Статус") or ""
                )
                needs_action = any(kw in status.lower() for kw in [
                    "подпис", "ожидает", "требует", "входящий", "получен", "новый"
                ]) or not status
                if needs_action:
                    amount = item.get("СуммаДокумента") or item.get("Сумма") or 0
                    docs.append({
                        "id": str(item.get("Ref_Key", "")),
                        "number": str(item.get("Number", "б/н")),
                        "date": str(item.get("Date", ""))[:10],
                        "status": status or "Входящий",
                        "amount": float(amount),
                        "counterparty_key": str(item.get("Контрагент_Key", ""))[:8],
                        "doc_type": entity.replace("Document_", ""),
                        "entity": entity,
                    })
            return True, docs
        return False, []

    async def sync_products(self, store_products: List) -> dict:
        """Full sync: pull from 1C and return mapping."""
        result = {"synced": 0, "errors": 0, "products": []}
        success, products_1c = await self.get_products(limit=1000)
        if not success:
            return result

        for p in products_1c:
            result["synced"] += 1
            result["products"].append(p)

        return result
