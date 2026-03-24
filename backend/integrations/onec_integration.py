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
        path = (
            f"odata/standard.odata/Catalog_Номенклатура"
            f"?$format=json&$top={limit}&$skip={offset}"
            f"&$select=Ref_Key,Code,Description,Артикул,ЕдиницаИзмерения_Key"
        )
        success, data = await self._request("GET", path)
        if not success:
            return False, []

        items = data.get("value", []) if isinstance(data, dict) else []
        products = []
        for item in items:
            if item.get("IsFolder"):
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

    async def create_product(self, product) -> Tuple[bool, Optional[dict]]:
        """Create a new product (nomenclature) in 1C."""
        payload = {
            "Description": product.name,
            "Артикул": product.article or "",
        }
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
        success, data = await self._request(
            "PATCH",
            f"odata/standard.odata/Catalog_Номенклатура(guid'{onec_id}')",
            json=payload,
        )
        return success, data

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
