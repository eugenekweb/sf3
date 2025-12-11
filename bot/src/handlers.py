from aiogram import Router, F
from aiogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from aiogram.filters import Command
import json
import logging
import os

logger = logging.getLogger(__name__)
router = Router()


class BotHandlers:
    """Обработчики событий бота"""

    def __init__(self, backend_url: str, bot_token: str):
        self.backend_url = backend_url
        self.bot_token = bot_token

    @staticmethod
    async def cmd_start(message: Message, backend_url: str, bot_token: str):
        """Команда /start"""
        user_id = message.from_user.id
        user_name = message.from_user.first_name or "User"

        text = (
            f"👋 Привет, {user_name}!\n\n"
            "Этот бот помогает извлечь список участников из экспорта истории Telegram-чата.\n\n"
            "📋 <b>Как использовать:</b>\n"
            "1. Экспортируйте историю чата в формате JSON\n"
            "2. Отправьте JSON файл(ы) напрямую в этот чат\n"
            "3. Бот обработает файлы и отправит результат\n\n"
            "⚠️ <i>Ограничение: файлы до 20 МБ каждый (лимит Telegram API)</i>\n"
            "📎 <i>Поддерживаются только JSON файлы экспорта Telegram</i>"
        )

        await message.answer(text, parse_mode="HTML")
        logger.info(f"User {user_id} started bot")

    @staticmethod
    async def handle_web_app_data(message: Message):
        """Обработка результата из WebApp"""
        if not message.web_app_data:
            return

        try:
            data = json.loads(message.web_app_data.data)
            user_id = data.get("user_id")

            logger.info(f"Received data from user {user_id}: {data}")

            if data.get("success"):
                await message.answer(f"✅ {data.get('message', 'Готово!')}")
            else:
                await message.answer(
                    f"❌ {data.get('message', 'Ошибка при обработке')}"
                )
        except Exception as e:
            logger.error(f"Error handling web app data: {e}")
            await message.answer("❌ Ошибка при обработке результата")

    @staticmethod
    async def handle_document(message: Message, backend_url: str, bot_token: str):
        """Обработка файла, отправленного напрямую в бота"""
        from aiogram import Bot
        import aiohttp
        import tempfile
        import os

        document = message.document

        # Проверка формата
        if not document.file_name or not document.file_name.endswith(".json"):
            await message.answer("❌ Пожалуйста, отправьте файл с расширением .json")
            return

        # Проверка размера (20 МБ лимит Telegram)
        max_size = 20 * 1024 * 1024  # 20 МБ
        if document.file_size and document.file_size > max_size:
            await message.answer(
                f"❌ Файл слишком большой ({document.file_size / 1024 / 1024:.1f} МБ). "
                f"Максимум 20 МБ.\n\n"
                f"💡 Для больших файлов используйте WebApp (настройте HTTPS URL в .env)"
            )
            return

        status_msg = await message.answer("⏳ Скачиваю и обрабатываю файл...")

        bot = Bot(token=bot_token)
        temp_path = None

        try:
            # Скачиваем файл
            file_info = await bot.get_file(document.file_id)
            file_path = file_info.file_path

            # Создаем временный файл
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
            temp_path = temp_file.name
            temp_file.close()

            await bot.download_file(file_path, temp_path)

            # Отправляем на сервер для обработки
            if backend_url:
                # Используем веб-сервер для обработки
                async with aiohttp.ClientSession() as session:
                    with open(temp_path, "rb") as f:
                        form_data = aiohttp.FormData()
                        form_data.add_field("user_id", str(message.from_user.id))
                        form_data.add_field("files", f, filename=document.file_name)

                        async with session.post(
                            f"{backend_url}/api/upload", data=form_data
                        ) as resp:
                            result = await resp.json()

                            if resp.status == 200:
                                # Не отправляем сообщение - результаты уже отправлены веб-сервером
                                # Просто логируем успех
                                logger.info(
                                    f"File processed successfully: {result.get('message', 'OK')}"
                                )
                            else:
                                await message.answer(
                                    f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}"
                                )
            else:
                # Обработка напрямую в боте (упрощенная версия)
                await message.answer(
                    "⚠️ Веб-сервер не настроен. Настройте BACKEND_URL в .env"
                )

        except Exception as e:
            logger.error(f"Error handling document: {e}", exc_info=True)
            await message.answer(f"❌ Ошибка при обработке файла: {str(e)}")

        finally:
            # Удаляем временный файл
            if temp_file and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            await status_msg.delete()


def register_handlers(dp, backend_url: str, bot_token: str):
    """Регистрация всех обработчиков"""

    @router.message(Command("start"))
    async def cmd_start_handler(message: Message):
        await BotHandlers.cmd_start(message, backend_url, bot_token)

    @router.message(F.document)
    async def document_handler(message: Message):
        await BotHandlers.handle_document(message, backend_url, bot_token)

    @router.message()
    async def any_message(message: Message):
        await BotHandlers.handle_web_app_data(message)

    dp.include_router(router)
