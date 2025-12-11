import asyncio
import logging
from src.utils import setup_logging, Config
from src.bot import TelegramBot
from src.handlers import register_handlers

setup_logging()
logger = logging.getLogger(__name__)

async def main():
    """Главная функция"""
    config = Config()
    
    bot = TelegramBot(config.BOT_TOKEN)
    register_handlers(bot.dp, config.BACKEND_URL, config.BOT_TOKEN)
    
    try:
        await bot.start_polling()
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())

