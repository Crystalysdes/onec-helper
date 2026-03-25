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
                return False, {"error": response.text[:200], "status": response.status_code}
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
        """Write retail price for a product in 1C price register."""
        from datetime import datetime as _dt
        period = _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        for register in ("InformationRegister_ЦеныНоменклатуры", "InformationRegister_Цены"):
            # 1. Try to find existing record to get the composite key fields
            path = (
                f"odata/standard.odata/{register}"
                f"?$format=json&$filter=Номенклатура_Key eq guid'{onec_id}'&$top=1"
            )
            success, data = await self._request("GET", path)
            if success and isinstance(data, dict):
                items = data.get("value", [])
                if items:
                    item = items[0]
                    price_type = item.get("ВидЦены_Key") or item.get("ТипЦен_Key")
                    currency = item.get("Валюта_Key")
                    old_period = item.get("Период", period)

                    # Build composite key for PATCH
                    key_parts = [f"Период=datetime'{old_period}'",
                                 f"Номенклатура_Key=guid'{onec_id}'"]
                    if price_type:
                        key_parts.append(f"ВидЦены_Key=guid'{price_type}'")
                    key = ",".join(key_parts)

                    payload = {"Цена": price, "Период": period}
                    if price_type:
                        payload["ВидЦены_Key"] = price_type
                    if currency:
                        payload["Валюта_Key"] = currency

                    ok, _ = await self._request(
                        "PATCH",
                        f"odata/standard.odata/{register}({key})",
                        json=payload,
                    )
                    if ok:
                        logger.info(f"1C price updated: {onec_id} → {price}")
                        return True

                # No existing record — try POST with minimal payload
                payload = {
                    "Номенклатура_Key": onec_id,
                    "Цена": price,
                    "Период": period,
                }
                ok, _ = await self._request("POST", f"odata/standard.odata/{register}", json=payload)
                if ok:
                    logger.info(f"1C price created: {onec_id} → {price}")
                    return True
        logger.warning(f"1C price set failed for onec_id={onec_id}")
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

    async def create_barcode(self, onec_id: str, barcode: str) -> bool:
        """Try to create a barcode record in 1C for the given product (Ref_Key=onec_id)."""
        entity_variants = [
            ("Catalog_ШтрихкодыНоменклатуры", "Владелец_Key", "Штрихкод"),
            ("Catalog_ШтрихкодыНоменклатуры", "Owner_Key", "Штрихкод"),
            ("Catalog_НоменклатураШтрихкоды", "Владелец_Key", "Штрихкод"),
        ]
        for entity, owner_field, bc_field in entity_variants:
            payload = {owner_field: onec_id, bc_field: barcode, "Description": barcode}
            success, data = await self._request(
                "POST", f"odata/standard.odata/{entity}", json=payload
            )
            if success:
                logger.info(f"1C barcode created: {barcode} → {onec_id} via {entity}")
                return True
        logger.warning(f"1C barcode create failed for {barcode}: no matching entity")
        return False

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
