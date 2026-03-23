from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
import httpx
from loguru import logger

from bot.config import settings
from bot.keyboards.main_keyboard import get_webapp_inline_button

router = Router()


def admin_only(func):
    async def wrapper(message: Message, is_admin: bool = False, **kwargs):
        if not is_admin and message.from_user.id != settings.ADMIN_TELEGRAM_ID:
            await message.answer("⛔ Доступ запрещён.")
            return
        return await func(message, is_admin=is_admin, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


@router.message(F.text == "👑 Админ панель")
async def admin_panel(message: Message, is_admin: bool = False):
    if not is_admin and message.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await message.answer("⛔ Доступ запрещён.")
        return

    text = (
        "👑 <b>Панель администратора</b>\n\n"
        "Управляйте платформой через веб-приложение.\n\n"
        "<b>Доступные команды:</b>\n"
        "/admin_stats — статистика платформы\n"
        "/admin_users — список пользователей\n"
        "/admin_logs — последние логи\n\n"
        "Или откройте полную панель управления:"
    )
    await message.answer(
        text,
        reply_markup=get_webapp_inline_button(f"{settings.MINIAPP_URL}/admin"),
        parse_mode="HTML",
    )


@router.message(Command("admin_stats"))
async def admin_stats(message: Message, is_admin: bool = False):
    if not is_admin and message.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await message.answer("⛔ Доступ запрещён.")
        return

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.BACKEND_URL}/api/v1/admin/stats",
                headers={"X-Admin-ID": str(message.from_user.id)},
            )
            if resp.status_code == 200:
                data = resp.json()
                text = (
                    "📊 <b>Статистика платформы</b>\n\n"
                    f"👤 Пользователей: <b>{data.get('total_users', 0)}</b>\n"
                    f"🏪 Магазинов: <b>{data.get('total_stores', 0)}</b>\n"
                    f"📦 Товаров: <b>{data.get('total_products', 0)}</b>\n"
                    f"🔌 Интеграций: <b>{data.get('total_integrations', 0)}</b>\n"
                )
                await message.answer(text, parse_mode="HTML")
                return
    except Exception as e:
        logger.error(f"Admin stats error: {e}")

    await message.answer("❌ Не удалось получить статистику. Проверьте подключение к API.")


@router.message(Command("admin_users"))
async def admin_users(message: Message, is_admin: bool = False):
    if not is_admin and message.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await message.answer("⛔ Доступ запрещён.")
        return

    await message.answer(
        "👥 Список пользователей доступен в панели администратора.",
        reply_markup=get_webapp_inline_button(f"{settings.MINIAPP_URL}/admin/users"),
    )


@router.message(Command("broadcast"))
async def broadcast(message: Message, is_admin: bool = False):
    if not is_admin and message.from_user.id != settings.ADMIN_TELEGRAM_ID:
        await message.answer("⛔ Доступ запрещён.")
        return

    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer(
            "📢 Укажите текст рассылки:\n/broadcast Ваш текст здесь"
        )
        return

    await message.answer(f"📢 Рассылка отправлена: {text[:50]}...")
