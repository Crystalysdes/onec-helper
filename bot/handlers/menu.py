from aiogram import Router, F
from aiogram.types import Message
import httpx
from loguru import logger

from bot.config import settings
from bot.keyboards.main_keyboard import get_main_menu_keyboard, get_webapp_inline_button

router = Router()


async def get_user_stats(telegram_id: int) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.BACKEND_URL}/api/v1/stores/",
                headers={"X-Telegram-ID": str(telegram_id)},
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.warning(f"Failed to get user stats: {e}")
    return {}


@router.message(F.text == "🛍 Открыть магазин")
async def open_shop(message: Message):
    await message.answer(
        "🚀 Открываю приложение...",
        reply_markup=get_webapp_inline_button(settings.MINIAPP_URL),
    )


@router.message(F.text == "📦 Мои магазины")
async def my_stores(message: Message):
    text = (
        "📦 <b>Управление магазинами</b>\n\n"
        "Откройте приложение чтобы управлять вашими магазинами и подключить 1С."
    )
    await message.answer(
        text,
        reply_markup=get_webapp_inline_button(f"{settings.MINIAPP_URL}/settings"),
        parse_mode="HTML",
    )


@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    text = (
        "📊 <b>Статистика</b>\n\n"
        "Откройте приложение для просмотра подробных отчётов по вашему магазину."
    )
    await message.answer(
        text,
        reply_markup=get_webapp_inline_button(f"{settings.MINIAPP_URL}/reports"),
        parse_mode="HTML",
    )


@router.message(F.text == "⚙️ Настройки")
async def settings_menu(message: Message):
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        "В настройках вы можете:\n"
        "• Подключить систему 1С\n"
        "• Управлять магазинами\n"
        "• Настроить синхронизацию\n\n"
        "Откройте приложение для изменения настроек."
    )
    await message.answer(
        text,
        reply_markup=get_webapp_inline_button(f"{settings.MINIAPP_URL}/settings"),
        parse_mode="HTML",
    )


@router.message(F.text == "❓ Помощь")
async def help_menu(message: Message):
    text = (
        "❓ <b>Помощь</b>\n\n"
        "<b>Как добавить товар:</b>\n"
        "1. Откройте приложение\n"
        "2. Перейдите в раздел «Товары»\n"
        "3. Нажмите «Добавить товар»\n"
        "4. Выберите способ добавления\n\n"
        "<b>Способы добавления товара:</b>\n"
        "📝 Вручную — заполните форму\n"
        "📷 Штрих-код — сканируйте камерой\n"
        "📸 Фото товара — AI распознает товар\n"
        "📄 Накладная — загрузите документ\n\n"
        "<b>Подключение 1С:</b>\n"
        "Перейдите в Настройки → Интеграция 1С\n\n"
        "По вопросам: /help"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(F.web_app_data)
async def handle_webapp_data(message: Message):
    """Handle data sent from the Mini App."""
    data = message.web_app_data.data
    logger.info(f"WebApp data from {message.from_user.id}: {data[:100]}")
    await message.answer(
        f"✅ Данные из приложения получены!\n\n"
        f"Продолжайте работу в приложении.",
    )
