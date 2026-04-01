import httpx
from typing import Tuple, List, Optional
from loguru import logger

_BASE_URL = "https://api.kontur.ru/market/v1"


class KonturMarketClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._headers = {
            "x-kontur-apikey": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> Tuple[bool, dict]:
        url = f"{_BASE_URL}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(method, url, headers=self._headers, **kwargs)
                if response.status_code in (200, 201, 204):
                    try:
                        return True, response.json() if response.content else {}
                    except Exception:
                        return True, {}
                if response.status_code == 401:
                    return False, {"error": "Неверный API-ключ (401 Unauthorized)"}
                if response.status_code == 403:
                    return False, {"error": "Нет доступа к методу (403 Forbidden)"}
                return False, {"error": response.text[:400], "status": response.status_code}
        except Exception as e:
            logger.error(f"KonturMarket request error [{method} {path}]: {e}")
            return False, {"error": str(e)}

    async def test_connection(self) -> Tuple[bool, str]:
        """Test API key validity by fetching shops list."""
        success, data = await self._request("GET", "/v1/shops")
        if success:
            shops = data if isinstance(data, list) else []
            if not shops:
                return True, "API-ключ действителен. Торговые точки не найдены — проверьте настройки Маркета."
            names = ", ".join(s.get("name", "—") for s in shops[:3])
            return True, f"Подключение к Контур.Маркет успешно. Торговых точек: {len(shops)} ({names})"
        error = data.get("error", "Неизвестная ошибка")
        return False, f"Ошибка подключения к Контур.Маркет: {error}"

    async def get_shops(self) -> Tuple[bool, List[dict]]:
        """Return list of shops available for this API key."""
        success, data = await self._request("GET", "/v1/shops")
        if not success:
            return False, []
        items = data if isinstance(data, list) else data.get("items", []) if isinstance(data, dict) else []
        return True, items

    async def get_products(self, shop_id: str) -> Tuple[bool, List[dict]]:
        """Fetch full product list for a shop."""
        success, data = await self._request("GET", f"/v1/shops/{shop_id}/products")
        if not success:
            logger.warning(f"KM get_products failed for shop {shop_id}: {data.get('error')}")
            return False, []
        items = data.get("items", []) if isinstance(data, dict) else data if isinstance(data, list) else []
        products = []
        for item in items:
            if item.get("isDeleted") or item.get("isArchived"):
                continue
            barcode = item.get("barcode") or None
            group = item.get("productGroup") or {}
            products.append({
                "kontur_id": str(item.get("id", "")),
                "name": item.get("name", "").strip(),
                "article": item.get("code") or None,
                "barcode": barcode,
                "price": item.get("price"),
                "category": group.get("name") if group else None,
            })
        return True, products

    async def get_stock_balances(self, shop_id: str) -> Tuple[bool, List[dict]]:
        """Fetch current stock balances for a shop."""
        success, data = await self._request("GET", f"/v1/shops/{shop_id}/product-rests")
        if not success:
            logger.warning(f"KM get_stock_balances failed for shop {shop_id}: {data.get('error')}")
            return False, []
        items = data.get("items", []) if isinstance(data, dict) else data if isinstance(data, list) else []
        return True, [
            {
                "kontur_id": str(item.get("productId", "")),
                "quantity": float(item.get("quantity", 0) or 0),
            }
            for item in items
            if item.get("productId")
        ]

    async def create_product(
        self,
        shop_id: str,
        name: str,
        price: Optional[float] = None,
        purchase_price: Optional[float] = None,
        barcode: Optional[str] = None,
        article: Optional[str] = None,
    ) -> Tuple[bool, dict]:
        """Create a new product in Kontour Market shop."""
        payload: dict = {"name": name, "type": "Product"}
        if price is not None:
            payload["price"] = price
        if barcode:
            payload["barcode"] = barcode
        if article:
            payload["code"] = article
        success, data = await self._request("POST", f"/v1/shops/{shop_id}/products", json=payload)
        if not success:
            logger.warning(f"KM create_product failed: {data.get('error')}")
        return success, data

    async def update_product(
        self,
        shop_id: str,
        product_id: str,
        name: Optional[str] = None,
        price: Optional[float] = None,
        barcode: Optional[str] = None,
        article: Optional[str] = None,
    ) -> Tuple[bool, dict]:
        """Patch an existing product in Kontour Market."""
        payload: dict = {}
        if name is not None:
            payload["name"] = name
        if price is not None:
            payload["price"] = price
        if barcode is not None:
            payload["barcode"] = barcode
        if article is not None:
            payload["code"] = article
        if not payload:
            return True, {}
        success, data = await self._request("PATCH", f"/v1/shops/{shop_id}/products/{product_id}", json=payload)
        if not success:
            logger.warning(f"KM update_product failed: {data.get('error')}")
        return success, data

    async def sync_cashboxes(self, shop_id: str, product_ids: Optional[List[str]] = None) -> bool:
        """Push products to cash registers. Empty list = push all."""
        payload = product_ids or []
        success, _ = await self._request("POST", f"/v1/shops/{shop_id}/products/syncCashboxes", json=payload)
        return success

    async def upsert_product(
        self,
        shop_id: str,
        name: str,
        price: Optional[float] = None,
        purchase_price: Optional[float] = None,
        barcode: Optional[str] = None,
        article: Optional[str] = None,
        existing_kontur_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Create or update product. Returns (success, kontur_id)."""
        if existing_kontur_id:
            ok, data = await self.update_product(shop_id, existing_kontur_id, name=name,
                                                  price=price, barcode=barcode, article=article)
            return ok, existing_kontur_id if ok else None
        else:
            ok, data = await self.create_product(shop_id, name=name, price=price,
                                                   purchase_price=purchase_price,
                                                   barcode=barcode, article=article)
            if ok and isinstance(data, dict):
                return True, str(data.get("id", ""))
            return False, None
