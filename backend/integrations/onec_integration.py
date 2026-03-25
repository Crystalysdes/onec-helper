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
        self, method: str, path: str, **kwargs
    ) -> Tuple[bool, Optional[dict]]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {**self._headers, **self._get_auth_header()}
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
        # All known entity names across different 1C configurations
        # owner_field candidates tried automatically from item keys
        entities_to_try = [
            "Catalog_ШтрихкодыНоменклатуры",    # Штрихкоды номенклатуры (УНФ / 1СФреш)
            "Catalog_НоменклатураШтрихкоды",    # Торговля
            "InformationRegister_ШтрихкодыНоменклатуры",
            "InformationRegister_Штрихкоды",
        ]
        # Possible field names for owner ref and barcode value
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
                # auto-detect owner field
                oid = ""
                for of in owner_fields:
                    if of in item and item[of]:
                        oid = str(item[of])
                        break
                # auto-detect barcode field
                bc = ""
                for bf in bc_fields:
                    if bf in item and str(item[bf]).strip().isdigit():
                        bc = str(item[bf]).strip()
                        break
                if oid and bc and oid not in result:
                    result[oid] = bc
            logger.info(f"1C barcodes loaded from {entity}: {len(result)} entries")
            return result
        logger.warning("1C barcodes: no barcode catalog found in OData")
        return {}

    async def get_entities(self) -> List[str]:
        """Return list of all published OData entity names."""
        success, data = await self._request("GET", "odata/standard.odata/?$format=json")
        if not success or not isinstance(data, dict):
            return []
        return [e.get("name", "") for e in data.get("value", []) if e.get("name")]

    async def get_all_prices(self) -> dict:
        """Fetch ALL prices from 1C in one request. Returns {onec_id: price}."""
        for register in ("InformationRegister_ЦеныНоменклатуры", "InformationRegister_Цены"):
            path = (
                f"odata/standard.odata/{register}"
                f"?$format=json&$top=50000&$select=Номенклатура_Key,Цена,ВидЦены_Key"
            )
            success, data = await self._request("GET", path)
            if not success or not isinstance(data, dict):
                continue
            items = data.get("value", [])
            if not items:
                continue
            prices: dict = {}
            for item in items:
                oid = str(item.get("Номенклатура_Key", "")).strip("{}")
                price = item.get("Цена") or item.get("Price")
                if oid and price is not None:
                    # keep the highest price (retail > purchase) as the primary price
                    if oid not in prices or float(price) > float(prices[oid]):
                        prices[oid] = float(price)
            logger.info(f"1C prices loaded from {register}: {len(prices)} entries")
            return prices
        return {}

    async def set_price(self, onec_id: str, price: float) -> bool:
        """Write retail price for a product in 1C price register.

        Strategy:
          1. Fetch ВидЦены_Key (price type) — mandatory dimension in 1C.
          2. Look for an existing record with this product+type → PATCH it.
          3. If none found → POST a new record.
          4. Fallback: repeat for alternate register names.
        """
        onec_id = str(onec_id).strip("{}")  # normalize GUID format
        from datetime import datetime as _dt
        period = _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        price_type_key = await self._get_or_fetch_price_type_key()

        # ── 1. PATCH Catalog_Номенклатура directly (confirmed working in 1C Fresh)
        for price_field in ("Цена", "ЦенаРозничная", "ЦенаЗакупка"):
            ok, resp = await self._request(
                "PATCH", f"odata/standard.odata/Catalog_Номенклатура(guid'{onec_id}')",
                json={price_field: price}
            )
            if ok:
                logger.info(f"1C price set via PATCH Catalog_Ном/{price_field}: {onec_id} → {price}")
                return True
            logger.warning(f"1C price PATCH Catalog_Ном/{price_field}: {resp}")

        # ── 2. InformationRegister fallback
        _zero = "00000000-0000-0000-0000-000000000000"
        vid_key = price_type_key or _zero
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

        # ── 1. PATCH Catalog_Номенклатура tabular section (подтверждено работает в 1C Fresh)
        for key_name, items in [
            ("ШтрихкодыНоменклатуры", [{"LineNumber": 1, "Штрихкод": barcode, "ТипШтрихкода": bc_type}]),
            ("ШтрихкодыНоменклатуры", [{"LineNumber": 1, "Штрихкод": barcode}]),
            ("Штрихкоды", [{"LineNumber": 1, "Штрихкод": barcode, "ТипШтрихкода": bc_type}]),
        ]:
            ok, resp = await self._request(
                "PATCH", f"odata/standard.odata/Catalog_Номенклатура(guid'{onec_id}')",
                json={key_name: items}
            )
            if ok:
                logger.info(f"1C barcode created (PATCH/{key_name}): {barcode} → {onec_id}")
                return True
            logger.warning(f"1C barcode PATCH/{key_name} failed: {resp}")

        # ── 2. InformationRegister POST fallback ────────────────────────────────
        for entity in ("InformationRegister_ШтрихкодыНоменклатуры", "InformationRegister_Штрихкоды"):
            for pl in [
                {"Номенклатура_Key": onec_id, "Штрихкод": barcode, "ТипШтрихкода": bc_type},
                {"Номенклатура_Key": onec_id, "Штрихкод": barcode},
            ]:
                ok, resp = await self._request("POST", f"odata/standard.odata/{entity}", json=pl)
                if ok:
                    logger.info(f"1C barcode created (register): {barcode} → {onec_id} via {entity}")
                    return True
                logger.warning(f"1C barcode register attempt ({entity}): {resp}")

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

        # ── GET the actual product to see what fields Catalog_Номенклатура has
        nom_fields = []
        ok, data = await self._request(
            "GET", f"odata/standard.odata/Catalog_Номенклатура(guid'{onec_id}')?$format=json"
        )
        if ok and isinstance(data, dict):
            nom_fields = [k for k in data.keys() if not k.startswith("odata") and
                          any(s in k.lower() for s in ("цен", "price", "штрих", "barcode"))]

        bc_results = []
        # ── 1. PATCH Catalog_Номенклатура tabular section (most reliable for 1C Fresh)
        for bc_pl in [
            {"ШтрихкодыНоменклатуры": [{"LineNumber": 1, "Штрихкод": test_barcode, "ТипШтрихкода": bc_type}]},
            {"ШтрихкодыНоменклатуры": [{"LineNumber": 1, "Штрихкод": test_barcode}]},
            {"Штрихкоды": [{"LineNumber": 1, "Штрихкод": test_barcode, "ТипШтрихкода": bc_type}]},
        ]:
            key_name = list(bc_pl.keys())[0]
            ok, resp = await self._request(
                "PATCH", f"odata/standard.odata/Catalog_Номенклатура(guid'{onec_id}')", json=bc_pl
            )
            bc_results.append({"entity": f"PATCH Catalog_Номенклатура/{key_name}",
                               "payload": str(list(bc_pl[key_name][0].keys())), "ok": ok, "resp": str(resp)[:600]})
            if ok:
                break
        # ── 2. Catalog variants
        for entity in ("Catalog_ШтрихкодыНоменклатуры", "Catalog_НоменклатураШтрихкоды"):
            for owner_field in ("Владелец_Key", "Owner_Key"):
                pl = {owner_field: onec_id, f"{owner_field[:-4]}_Type": "StandardODATA.Catalog_Номенклатура",
                      "Штрихкод": test_barcode, "ТипШтрихкода": bc_type}
                ok, resp = await self._request("POST", f"odata/standard.odata/{entity}", json=pl)
                bc_results.append({"entity": entity, "payload": "catalog+type", "ok": ok, "resp": str(resp)[:600]})
        # ── 3. InformationRegister POST variants
        for entity in ("InformationRegister_ШтрихкодыНоменклатуры", "InformationRegister_Штрихкоды"):
            for pl in [
                {"Номенклатура_Key": onec_id, "Штрихкод": test_barcode},
                {"Номенклатура_Key": onec_id, "Штрихкод": test_barcode, "ТипШтрихкода": bc_type},
                {"Период": period, "Номенклатура_Key": onec_id, "Штрихкод": test_barcode},
            ]:
                ok, resp = await self._request("POST", f"odata/standard.odata/{entity}", json=pl)
                bc_results.append({"entity": entity, "payload": str(list(pl.keys())), "ok": ok, "resp": str(resp)[:600]})
                if ok:
                    break

        price_results = []
        period0 = "0001-01-01T00:00:00"
        for register in ("InformationRegister_ЦеныНоменклатуры", "InformationRegister_Цены"):
            vid = price_type_key or _zero
            for pl in [
                {"Период": period, "Номенклатура_Key": onec_id, "Цена": test_price,
                 "ВидЦены_Key": vid, "Характеристика_Key": _zero, "Упаковка_Key": _zero},
                {"Период": period, "Номенклатура_Key": onec_id, "Цена": test_price, "ВидЦены_Key": vid},
                {"Период": period0, "Номенклатура_Key": onec_id, "Цена": test_price,
                 "ВидЦены_Key": vid, "Характеристика_Key": _zero, "Упаковка_Key": _zero},
                {"Период": period0, "Номенклатура_Key": onec_id, "Цена": test_price, "ВидЦены_Key": vid},
            ]:
                ok, resp = await self._request("POST", f"odata/standard.odata/{register}", json=pl)
                price_results.append({"register": register, "payload": str(list(pl.keys())),
                                      "ok": ok, "resp": str(resp)[:600]})
                if ok:
                    break
        # PATCH Catalog_Номенклатура with direct price field (may be silently ignored)
        for price_field in ("Цена", "ЦенаРозничная", "ЦенаЗакупка"):
            ok, resp = await self._request(
                "PATCH", f"odata/standard.odata/Catalog_Номенклатура(guid'{onec_id}')",
                json={price_field: test_price}
            )
            price_results.append({"register": f"PATCH Catalog_Ном/{price_field}",
                                   "payload": price_field, "ok": ok, "resp": str(resp)[:600]})
            if ok:
                break

        # Document_УстановкаЦенНоменклатуры — the standard 1C way to set prices
        doc_date = period
        vid = price_type_key or _zero
        line = {"LineNumber": 1, "Номенклатура_Key": onec_id, "Цена": test_price}
        for doc_entity in ("Document_УстановкаЦенНоменклатуры", "Document_УстановкаЦен"):
            for tab_key in ("Товары", "ТоварыУслуги", "Строки"):
                base = {"Дата": doc_date, "ВидЦены_Key": vid, tab_key: [line]}
                if org_key:
                    base["Организация_Key"] = org_key
                ok, resp = await self._request("POST", f"odata/standard.odata/{doc_entity}", json=base)
                price_results.append({
                    "register": doc_entity,
                    "payload": f"org={'yes' if org_key else 'no'}+{tab_key}",
                    "ok": ok, "resp": str(resp)[:600],
                })
                if ok:
                    break
            else:
                continue
            break

        return {
            "onec_id": onec_id,
            "org_key": org_key,
            "price_types_found": [t.get("Description") for t in price_types],
            "price_type_key": price_type_key,
            "nom_price_barcode_fields": nom_fields,
            "existing_barcode_fields": existing_bc,
            "existing_price_fields": existing_price,
            "existing_bc_for_product": existing_bc_for_product,
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
