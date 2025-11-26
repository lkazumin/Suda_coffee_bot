from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from suda_bot.database import engine, async_session
from suda_bot.middleware import DatabaseSessionMiddleware
from suda_bot.handlers import user_router, barista_router
from suda_bot.database import init_db
from suda_bot.config import TELEGRAM_BOT_TOKEN
from suda_bot.scheduler import setup_scheduler

async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрируем middleware
    dp.message.middleware(DatabaseSessionMiddleware(async_session))
    dp.callback_query.middleware(DatabaseSessionMiddleware(async_session))

    # Подключаем роутеры
    dp.include_router(user_router)
    dp.include_router(barista_router)

    await init_db()

    # Запускаем планировщик
    setup_scheduler(async_session)

    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())