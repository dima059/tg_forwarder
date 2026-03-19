import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"
HOST = "0.0.0.0"
PORT = int(os.getenv('PORT', 8080))

SECRET_TOKEN = BOT_TOKEN.split(':')[1] if BOT_TOKEN and ':' in BOT_TOKEN else None

# === НАСТРОЙКИ ПРОКСИ ===
PROXY_URL = os.environ.get("PROXY_URL")  # HTTP прокси
# или
# PROXY_URL = os.environ.get("PROXY_URL_SOCKS5")  # SOCKS5 прокси
# ========================

SOURCE_CHANNEL_ID = int(os.environ.get("SOURCE_CHANNEL_ID")) #1635
TARGET_GROUP_ID = int(os.environ.get("TARGET_GROUP_ID")) #0451

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dp = Dispatcher()

# Хранилище последних ID сообщений, чтобы избежать дубликатов
processed_messages = set()
MAX_STORED_IDS = 1000

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("🤖 Бот запущен и готов пересылать сообщения.")

@dp.message(Command("status"))
async def cmd_status(message: Message):
    await message.answer(
        f"📊 Статус:\n"
        f"Канал: {SOURCE_CHANNEL_ID}\n"
        f"Группа: {TARGET_GROUP_ID}\n"
        f"Обработано сообщений: {len(processed_messages)}"
    )

@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    global processed_messages
    processed_messages.clear()
    await message.answer("✅ История обработанных сообщений очищена.")

@dp.channel_post()
async def forward_from_channel(message: Message):
    global processed_messages
    logger.info(f"📨 Пост из канала: {message.message_id}, chat_id={message.chat.id}")
    
    if message.chat.id != SOURCE_CHANNEL_ID:
        logger.warning(f"⚠️ Пост из другого канала: {message.chat.id}")
        return

    if message.message_id in processed_messages:
        logger.info(f"⚠️ Сообщение {message.message_id} уже обработано")
        return

    try:
        await message.copy_to(chat_id=TARGET_GROUP_ID)
        processed_messages.add(message.message_id)

        if len(processed_messages) > MAX_STORED_IDS:
            processed_messages = set(list(processed_messages)[-MAX_STORED_IDS:])

        logger.info(f"✅ Сообщение {message.message_id} переслано")
    except Exception as e:
        logger.error(f"❌ Ошибка при пересылке: {e}", exc_info=True)

async def on_startup(bot: Bot):
    """Установка webhook при запуске"""
    await bot.set_webhook(
        WEBHOOK_URL,
        allowed_updates=dp.resolve_used_update_types(),
        secret_token=SECRET_TOKEN
    )
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(bot: Bot):
    """Удаление webhook при остановке"""
    await bot.delete_webhook()
    logger.info("✅ Webhook удалён")

async def main():
    logger.info(f"🚀 Запуск бота (Webhook mode) на порту {PORT}...")

    # Валидация обязательных переменных
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не установлен!")
        return
    
    if not WEBHOOK_URL:
        logger.error("❌ WEBHOOK_URL не установлен!")
        return

    # Создаём сессию (прокси нужен только для исходящих запросов)
    session = AiohttpSession(
        proxy=PROXY_URL if PROXY_URL else None,
        timeout=60
    )
    bot = Bot(token=BOT_TOKEN, session=session)
    
    # Регистрируем хуки старта/остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Создаём aiohttp приложение
    app = web.Application()

    # Настраиваем обработчик webhook
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=SECRET_TOKEN  # Для безопасности
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    # Настраиваем приложение
    setup_application(app, dp, bot=bot)
    
    # Запускаем сервер
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()
    
    logger.info(f"🌐 Сервер запущен на {HOST}:{PORT}")
    logger.info(f"🔗 Webhook URL: {WEBHOOK_URL}")
    
    # Держим сервер запущенным
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logger.info("Остановка сервера...")
    finally:
        await runner.cleanup()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
