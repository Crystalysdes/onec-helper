import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from loguru import logger

from bot.config import settings
from bot.handlers import start_router, menu_router, admin_router
from bot.middlewares import AuthMiddleware


async def main():
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.message.middleware(AuthMiddleware())

    dp.include_router(start_router)
    dp.include_router(menu_router)
    dp.include_router(admin_router)

    await bot.delete_webhook(drop_pending_updates=True)

    logger.info(f"Starting bot @{settings.BOT_USERNAME}...")
    logger.info(f"Admin ID: {settings.ADMIN_TELEGRAM_ID}")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
