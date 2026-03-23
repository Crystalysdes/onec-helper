import uuid
import httpx
from loguru import logger
from backend.config import settings

YOOKASSA_BASE = "https://api.yookassa.ru/v3"
PRICE = 2499.00
CURRENCY = "RUB"
DESCRIPTION = "Подписка 1C Helper — 1 месяц"


def _auth():
    return (settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY)


async def create_payment(
    amount: float,
    description: str,
    return_url: str,
    metadata: dict,
    save_payment_method: bool = True,
    idempotency_key: str = None,
) -> dict:
    """Create a new YooKassa payment and return the full response dict."""
    key = idempotency_key or str(uuid.uuid4())
    payload = {
        "amount": {"value": f"{amount:.2f}", "currency": CURRENCY},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": description,
        "save_payment_method": save_payment_method,
        "metadata": metadata,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{YOOKASSA_BASE}/payments",
            json=payload,
            auth=_auth(),
            headers={"Idempotence-Key": key},
            timeout=20,
        )
    resp.raise_for_status()
    return resp.json()


async def create_auto_payment(
    amount: float,
    payment_method_id: str,
    description: str,
    metadata: dict,
    idempotency_key: str = None,
) -> dict:
    """Create an automatic recurring payment using a saved payment method."""
    key = idempotency_key or str(uuid.uuid4())
    payload = {
        "amount": {"value": f"{amount:.2f}", "currency": CURRENCY},
        "capture": True,
        "payment_method_id": payment_method_id,
        "description": description,
        "metadata": metadata,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{YOOKASSA_BASE}/payments",
            json=payload,
            auth=_auth(),
            headers={"Idempotence-Key": key},
            timeout=20,
        )
    resp.raise_for_status()
    return resp.json()


async def get_payment(payment_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{YOOKASSA_BASE}/payments/{payment_id}",
            auth=_auth(),
            timeout=10,
        )
    resp.raise_for_status()
    return resp.json()


def subscription_price(discount_percent: int = 0) -> float:
    if discount_percent <= 0:
        return PRICE
    return round(PRICE * (1 - discount_percent / 100), 2)
