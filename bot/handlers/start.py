import httpx
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.filters import CommandObject
from loguru import logger

from bot.config import settings
from bot.keyboards.main_keyboard import get_main_menu_keyboard, get_admin_keyboard

router = Router()


def get_greeting_name(user) -> str:
    if user.first_name:
        return user.first_name
    if user.username:
        return f"@{user.username}"
    return "друг"


async def _notify_backend_referral(referral_code: str, telegram_id: int):
    """Notify backend to apply referral code for a new user."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{settings.BACKEND_URL}/api/v1/subscriptions/apply-referral",
                params={"code": referral_code, "telegram_id": telegram_id},
            )
    except Exception as e:
        logger.warning(f"Could not apply referral code {referral_code}: {e}")


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject = None, is_admin: bool = False):
    name = get_greeting_name(message.from_user)
    is_adm = is_admin or message.from_user.id == settings.ADMIN_TELEGRAM_ID

    referral_code = None
    if command and command.args and command.args.startswith("ref_"):
        referral_code = command.args[4:]

    is_new_user_text = (
        f"\n\n🎁 <b>Пробный период: 7 дней бесплатно!</b>\n"
        f"После окончания пробного периода подписка стоит <b>2 499 ₽/мес</b>.\n"
        f"Подключите в приложении в разделе Настройки → Подписка."
    ) if not referral_code else (
        f"\n\n🎁 <b>Пробный период: 7 дней бесплатно!</b>\n"
        f"Реферальный код <code>{referral_code}</code> будет применён автоматически."
    )

    welcome_text = (
        f"👋 Привет, {name}!\n\n"
        f"Я <b>1С Хелпер</b> — ваш AI-ассистент для управления товарами.\n\n"
        f"Что я умею:\n"
        f"• 📦 Добавлять товары вручную или по фото\n"
        f"• 📷 Сканировать штрих-коды\n"
        f"• 📄 Обрабатывать накладные через OCR + AI\n"
        f"• 🔄 Синхронизировать данные с 1С\n"
        f"• 📊 Показывать отчёты по остаткам\n"
        f"{is_new_user_text}\n\n"
        f"Нажмите кнопку <b>«🛍 Открыть магазин»</b> чтобы начать работу."
    )

    keyboard = get_admin_keyboard() if is_adm else get_main_menu_keyboard()
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")
    logger.info(f"User {message.from_user.id} started the bot (ref={referral_code})")


@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "📚 <b>Справка по боту</b>\n\n"
        "<b>Команды:</b>\n"
        "/start — Главное меню\n"
        "/help — Справка\n"
        "/shop — Открыть приложение\n\n"
        "<b>Возможности приложения:</b>\n\n"
        "🛍 <b>Дашборд</b> — общая статистика магазина\n"
        "📦 <b>Товары</b> — список всех товаров с поиском\n"
        "➕ <b>Добавить товар</b> — 4 способа добавления:\n"
        "   • Вручную через форму\n"
        "   • Сканирование штрих-кода камерой\n"
        "   • Распознавание фото товара\n"
        "   • Загрузка накладной (OCR + AI)\n"
        "📊 <b>Отчёты</b> — остатки, ценность склада\n"
        "⚙️ <b>Настройки</b> — подключение 1С\n\n"
        "По вопросам: @oneshelperbot"
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("shop"))
async def cmd_shop(message: Message):
    from bot.keyboards.main_keyboard import get_webapp_inline_button
    await message.answer(
        "🚀 Нажмите кнопку ниже чтобы открыть приложение:",
        reply_markup=get_webapp_inline_button(),
    )
