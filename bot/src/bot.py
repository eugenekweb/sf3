from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
import logging

logger = logging.getLogger(__name__)

class TelegramBot:
    """Основной класс бота"""
    
    def __init__(self, token: str):
        self.token = token
        self.bot = Bot(token=token)
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
    
    async def start_polling(self):
        """Запуск polling"""
        logger.info("🤖 Bot started polling")
        try:
            await self.dp.start_polling(self.bot)
        except Exception as e:
            logger.error(f"Error in polling: {e}")
        finally:
            await self.bot.session.close()
    
    async def close(self):
        """Закрытие бота"""
        await self.bot.session.close()

