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
    def _webapp_keyboard(backend_url: str | None) -> InlineKeyboardMarkup | None:
        """Кнопка для открытия WebApp, если URL задан"""
        if not backend_url:
            return None
        # Добавляем слэш, чтобы гарантированно открыть корень с формой
        url = backend_url.rstrip("/") + "/"
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🌐 Открыть WebApp",
                        web_app=WebAppInfo(url=url),
                    )
                ]
            ]
        )

    @staticmethod
    async def cmd_start(message: Message, backend_url: str, bot_token: str):
        """Команда /start"""
        user_id = message.from_user.id
        user_name = message.from_user.first_name or "User"

        text = (
            f"👋 Привет, {user_name}!\n\n"
            "Загружай экспорт чата через WebApp (HTTPS), так проходят и большие файлы.\n"
            "Если отправлять файл прямо боту, сработает лимит Telegram 20 МБ.\n\n"
            "📋 <b>Как использовать:</b>\n"
            "1) Экспортируй историю чата в JSON\n"
            "2) Нажми кнопку ниже «Открыть WebApp»\n"
            "3) Загрузись через форму, дождись результатов\n\n"
            "⚠️ Ограничение Telegram: в личку >20 МБ не принимаются, поэтому работаем через WebApp."
        )

        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=BotHandlers._webapp_keyboard(backend_url),
        )
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
        """
        Приём файлов в личку отключаем, чтобы не упираться в лимит 20 МБ.
        Направляем пользователя в WebApp по HTTPS.
        """
        if backend_url:
            url = backend_url.rstrip("/") + "/"
            await message.answer(
                "❌ Приём файлов прямо в бота отключён, используйте WebApp.\n"
                f"🌐 Открыть WebApp: {url}",
                reply_markup=BotHandlers._webapp_keyboard(backend_url),
            )
        else:
            await message.answer(
                "⚠️ BACKEND_URL не настроен. Укажите публичный HTTPS в переменной BACKEND_URL."
            )


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
