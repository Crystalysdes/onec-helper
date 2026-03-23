from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)
from bot.config import settings


def get_main_menu_keyboard(miniapp_url: str = None) -> ReplyKeyboardMarkup:
    url = miniapp_url or settings.MINIAPP_URL
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="🛍 Открыть магазин",
                    web_app=WebAppInfo(url=url),
                )
            ],
            [
                KeyboardButton(text="📦 Мои магазины"),
                KeyboardButton(text="⚙️ Настройки"),
            ],
            [
                KeyboardButton(text="📊 Статистика"),
                KeyboardButton(text="❓ Помощь"),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def get_admin_keyboard(miniapp_url: str = None) -> ReplyKeyboardMarkup:
    url = miniapp_url or settings.MINIAPP_URL
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="🛍 Открыть магазин",
                    web_app=WebAppInfo(url=url),
                )
            ],
            [
                KeyboardButton(text="📦 Мои магазины"),
                KeyboardButton(text="⚙️ Настройки"),
            ],
            [
                KeyboardButton(text="📊 Статистика"),
                KeyboardButton(text="❓ Помощь"),
            ],
            [
                KeyboardButton(text="👑 Админ панель"),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_back_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_webapp_inline_button(url: str = None) -> InlineKeyboardMarkup:
    app_url = url or settings.MINIAPP_URL
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Открыть приложение",
                    web_app=WebAppInfo(url=app_url),
                )
            ]
        ]
    )
