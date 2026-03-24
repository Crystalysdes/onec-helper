import asyncio
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import httpx
from loguru import logger

from bot.config import settings

router = Router()

_notified_doc_ids: set = set()


def _edo_keyboard(docs: list) -> InlineKeyboardMarkup:
    buttons = []
    for doc in docs[:5]:
        label = f"📄 №{doc['number']} — {doc['amount']:,.0f} ₽" if doc.get("amount") else f"📄 №{doc['number']}"
        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"edo_detail:{doc['id'][:20]}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


_doc_cache: dict = {}


async def poll_edo_with_cache(bot: Bot) -> None:
    """Wrapper that caches full doc data for detail view."""
    while True:
        try:
            token = settings.SECRET_KEY[:16] if hasattr(settings, "SECRET_KEY") else ""
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    f"{settings.BACKEND_URL}/api/v1/stores/edo-check",
                    params={"internal_token": token},
                )
                if resp.status_code != 200:
                    await asyncio.sleep(900)
                    continue

                data = resp.json()
                for item in data.get("notifications", []):
                    telegram_id = item["telegram_id"]
                    store_name = item["store_name"]
                    docs = item["documents"]

                    new_docs = [d for d in docs if d["id"] not in _notified_doc_ids]
                    if not new_docs:
                        continue

                    for doc in new_docs:
                        _notified_doc_ids.add(doc["id"])
                        _doc_cache[doc["id"][:20]] = doc

                    count = len(new_docs)
                    text = (
                        f"📬 <b>ЭДО: новые документы</b>\n"
                        f"Магазин: <b>{store_name}</b>\n\n"
                        f"Найдено <b>{count}</b> документ(ов), требующих внимания.\n"
                        f"Нажмите чтобы ознакомиться:"
                    )
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=text,
                        parse_mode="HTML",
                        reply_markup=_edo_keyboard(new_docs),
                    )
                    logger.info(f"Sent {count} EDO notifications to {telegram_id}")

        except Exception as e:
            logger.error(f"EDO poll error: {e}")

        await asyncio.sleep(900)


@router.callback_query(F.data.startswith("edo_detail:"))
async def edo_detail(callback: CallbackQuery):
    doc_key = callback.data.split(":", 1)[1]
    doc = _doc_cache.get(doc_key)

    if not doc:
        await callback.answer("Документ недоступен (перезапустите бота)", show_alert=True)
        return

    amount_str = f"{doc.get('amount', 0):,.2f} ₽" if doc.get("amount") else "не указана"
    status_str = doc.get("status") or "—"
    date_str = doc.get("date") or "—"
    doc_type = doc.get("doc_type", "Документ").replace("_", " ")

    text = (
        f"📄 <b>{doc_type}</b>\n\n"
        f"Номер: <b>№{doc.get('number', '—')}</b>\n"
        f"Дата: {date_str}\n"
        f"Статус: <i>{status_str}</i>\n"
        f"Сумма: <b>{amount_str}</b>\n\n"
        f"ℹ️ Для подписания документа откройте 1C:Fresh и найдите документ по номеру."
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()
