from aiogram import Router, F
from aiogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    CallbackQuery,
)
from aiogram.filters import Command
import json
import logging
import os
import requests
import aiohttp
import tempfile
from src.utils import Config as BotConfig

logger = logging.getLogger(__name__)
router = Router()


class BotHandlers:
    """Обработчики событий бота"""

    def __init__(self, backend_url: str, bot_token: str):
        self.backend_url = backend_url
        self.bot_token = bot_token

    @staticmethod
    async def _webapp_keyboard(
        backend_url: str | None, webapp_disabled: bool = False
    ) -> InlineKeyboardMarkup | None:
        """Кнопка для открытия WebApp, если URL задан и веб-апп не отключен"""
        if not backend_url or webapp_disabled:
            return None
        # Проверяем доступность URL асинхронно (не блокируем event loop)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    backend_url, timeout=aiohttp.ClientTimeout(total=2)
                ) as response:
                    if response.status >= 400:
                        logger.warning(f"BACKEND_URL недоступен: {backend_url}")
                        return None
        except Exception as e:
            logger.warning(f"BACKEND_URL недоступен: {backend_url}, ошибка: {e}")
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
            "3) <b>При первом открытии появится страница Tuna с предупреждением:</b>\n"
            '   • На странице будет текст: "Вы собираетесь посетить [домен].ru.tuna.am"\n'
            "   • И предупреждение о безопасности\n"
            "   • <b>Нажми кнопку «Посетить»</b> для продолжения\n"
            "   • Это нормально — так работает туннель Tuna (безопасно)\n"
            "4) В открывшемся окне выбери или перетащи JSON файлы\n"
            "5) Нажми «Загрузить и обработать», дождись результатов\n\n"
            "⚠️ Ограничение Telegram: в личку >20 МБ не принимаются, поэтому работаем через WebApp."
        )

        # Учитываем настройки веб-апп
        webapp_disabled = BotConfig.WEBAPP_DISABLED
        keyboard = await BotHandlers._webapp_keyboard(backend_url, webapp_disabled)
        if keyboard:
            # Добавляем кнопку Помощь
            keyboard.inline_keyboard.append(
                [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
            )

        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        logger.info(f"User {user_id} started bot")

    @staticmethod
    async def cmd_help(message: Message, backend_url: str):
        """Команда /help - инструкция по использованию"""
        text = (
            "📖 <b>Инструкция по использованию бота</b>\n\n"
            "🔹 <b>Шаг 1: Экспорт истории чата</b>\n"
            "1. Откройте Telegram Desktop\n"
            "2. Откройте нужный чат\n"
            "3. Нажмите на три точки → Экспорт истории чата\n"
            "4. Выберите формат <b>JSON</b> (обязательно!)\n"
            "5. Снимите галочки с медиафайлов (чтобы уменьшить размер)\n"
            "6. Нажмите Экспорт и сохраните файл(ы)\n\n"
            "🔹 <b>Шаг 2: Загрузка в бота</b>\n"
            "1. Нажмите кнопку Открыть WebApp\n"
            "2. При первом открытии появится страница сервиса Tuna с предупреждением:\n"
            '   • На странице будет текст: "Вы собираетесь посетить [домен].ru.tuna.am"\n'
            "   • И предупреждение о безопасности\n"
            "   • <b>Нажмите кнопку «Посетить»</b> для продолжения\n"
            "   • Это нормально — так работает туннель Tuna (безопасно)\n"
            "3. В открывшемся окне выберите или перетащите JSON файлы\n"
            "4. Можно загрузить до 10 файлов за раз\n"
            "5. Нажмите Загрузить и обработать\n\n"
            "🔹 <b>Шаг 3: Получение результата</b>\n"
            "• Если участников меньше 50: получите текстовый список\n"
            "• Если участников 50 и больше: получите Excel файл\n\n"
            "📋 <b>Требования к файлам:</b>\n"
            "• Формат: только JSON\n"
            "• Кодировка: UTF-8\n"
            "• Размер: до 2 ГБ каждый\n"
            "• Количество: максимум 10 файлов\n\n"
            "⚠️ <b>Важно:</b>\n"
            "• Файлы должны быть экспортом из Telegram Desktop\n"
            "• Структура: name, type, id, messages\n"
            "• Файлы не сохраняются на сервере"
        )

        webapp_disabled = BotConfig.WEBAPP_DISABLED
        keyboard = await BotHandlers._webapp_keyboard(backend_url, webapp_disabled)
        if keyboard:
            keyboard.inline_keyboard.append(
                [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
            )

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    @staticmethod
    async def handle_web_app_data(message: Message):
        """Обработка результата из WebApp"""
        if not message.web_app_data:
            return

        try:
            data = json.loads(message.web_app_data.data)
            user_id = data.get("user_id")
            success = data.get("success")

            # Детальное логирование только если включено
            from src.utils import Config as BotConfig

            if BotConfig.VERBOSE_LOGGING:
                logger.info(f"Received data from user {user_id}: {data}")
            else:
                logger.info(f"Received data from user {user_id}: success={success}")

            if success:
                await message.answer(f"✅ {data.get('message', 'Готово!')}")
            else:
                await message.answer(
                    f"❌ {data.get('message', 'Ошибка при обработке')}"
                )
        except Exception as e:
            logger.error(f"Error handling web app data: {e}")
            await message.answer("❌ Ошибка при обработке результата")

    @staticmethod
    async def handle_document(
        message: Message,
        backend_url: str,
        bot_token: str,
        webapp_disabled: bool = False,
        webapp_only: bool = False,
    ):
        """
        Обработка загрузки документов.
        Если WEBAPP_ONLY=true - принимаем файлы только через веб-апп.
        Если WEBAPP_DISABLED=true - принимаем файлы только напрямую в бота.
        """
        if webapp_only:
            # Только через веб-апп
            if backend_url:
                # При отклонении прямой загрузки всегда показываем кнопку WebApp,
                # игнорируя webapp_disabled (иначе пользователь останется без способа загрузить файлы)
                keyboard = await BotHandlers._webapp_keyboard(
                    backend_url, webapp_disabled=False
                )
                await message.answer(
                    "❌ Приём файлов прямо в бота отключён, используйте WebApp.",
                    reply_markup=keyboard,
                )
                return
            else:
                await message.answer(
                    "⚠️ BACKEND_URL не настроен. Укажите публичный HTTPS в переменной BACKEND_URL."
                )
                return
        elif webapp_disabled:
            # Только напрямую в бота (старый режим)
            await BotHandlers._process_document_directly(message, bot_token)
        else:
            # Оба метода работают
            # Проверяем размер файла: если > 20 МБ и backend_url доступен - предлагаем WebApp
            file_size = message.document.file_size if message.document else None
            if backend_url and file_size and file_size > 20 * 1024 * 1024:
                # Файл слишком большой для прямой загрузки, предлагаем WebApp
                keyboard = await BotHandlers._webapp_keyboard(backend_url, webapp_disabled=False)
                await message.answer(
                    f"⚠️ Файл слишком большой ({file_size / 1024 / 1024:.1f} МБ). "
                    f"Telegram API ограничивает прямую загрузку до 20 МБ.\n\n"
                    f"Используйте WebApp для загрузки больших файлов:",
                    reply_markup=keyboard,
                )
            else:
                # Файл подходит для прямой загрузки или backend_url недоступен
                # Обрабатываем напрямую (с проверкой размера внутри функции)
                await BotHandlers._process_document_directly(message, bot_token)

    @staticmethod
    async def _process_document_directly(message: Message, bot_token: str):
        """Обработка файла напрямую через внутренний API (без промежуточных сообщений)"""
        try:
            if not message.document:
                await message.answer("❌ Файл не найден в сообщении.")
                return

            # Проверка расширения
            if (
                not message.document.file_name
                or not message.document.file_name.lower().endswith(".json")
            ):
                file_name = message.document.file_name or "файл"
                await message.answer(
                    f"❌ Файл {file_name}: поддерживаются только JSON файлы."
                )
                return

            # Проверка размера (лимит Telegram API - 20 МБ)
            if (
                message.document.file_size
                and message.document.file_size > 20 * 1024 * 1024
            ):
                await message.answer(
                    f"❌ Файл слишком большой ({message.document.file_size / 1024 / 1024:.1f} МБ). "
                    f"Максимум 20 МБ для прямой загрузки. Используйте WebApp для больших файлов."
                )
                return

            # Скачиваем файл (без промежуточных сообщений)
            bot = message.bot
            file = await bot.get_file(message.document.file_id)

            # Создаем временный файл без открытого дескриптора (для совместимости с Windows)
            temp_fd, temp_path = tempfile.mkstemp(suffix=".json")
            os.close(temp_fd)  # Закрываем дескриптор сразу после создания
            await bot.download_file(file.file_path, temp_path)

            user_id = message.from_user.id

            # Отправляем на обработку через внутренний API
            # Используем внутренний Docker URL
            api_url = os.getenv("WEB_API_URL", "http://web:5000/api/upload")

            # Используем таймаут из конфигурации (по умолчанию 5 минут)
            from src.utils import Config as BotConfig

            timeout = aiohttp.ClientTimeout(total=BotConfig.UPLOAD_TIMEOUT)
            
            # Читаем файл в память для передачи через aiohttp
            with open(temp_path, "rb") as f:
                file_content = f.read()
            
            # Используем aiohttp для асинхронной загрузки файла
            async with aiohttp.ClientSession(timeout=timeout) as session:
                form_data = aiohttp.FormData()
                # Не указываем content_type - aiohttp/Flask автоматически определят тип файла
                # Указание 'application/json' мешает Flask распознать поле как файл в request.files
                form_data.add_field('files', file_content, filename=message.document.file_name)
                form_data.add_field('user_id', str(user_id))
                
                async with session.post(api_url, data=form_data) as response:
                    response_status = response.status
                    response_content = await response.read()

            # Удаляем временный файл
            try:
                os.unlink(temp_path)
            except OSError as e:
                logger.warning(f"Could not delete temp file {temp_path}: {e}")

            # Отправляем только один ответ - результат или ошибку
            if response_status == 200:
                # Результат уже отправлен через TelegramSender в app.py, не дублируем
                pass
            else:
                try:
                    error_data = json.loads(response_content.decode('utf-8')) if response_content else {}
                except:
                    error_data = {}
                error_msg = error_data.get("error", "Неизвестная ошибка при обработке")
                await message.answer(f"❌ Ошибка: {error_msg}")

        except Exception as e:
            logger.error(f"Error processing document directly: {e}", exc_info=True)
            await message.answer(f"❌ Ошибка при обработке файла: {str(e)}")


def register_handlers(dp, backend_url: str, bot_token: str):
    """Регистрация всех обработчиков"""
    webapp_disabled = BotConfig.WEBAPP_DISABLED
    webapp_only = BotConfig.WEBAPP_ONLY

    @router.message(Command("start"))
    async def cmd_start_handler(message: Message):
        await BotHandlers.cmd_start(message, backend_url, bot_token)

    @router.message(Command("help"))
    async def cmd_help_handler(message: Message):
        await BotHandlers.cmd_help(message, backend_url)

    @router.callback_query(F.data == "help")
    async def help_callback_handler(callback: CallbackQuery):
        if callback.message:
            # Если есть сообщение - отвечаем без параметров и отправляем help
            await callback.answer()
            await BotHandlers.cmd_help(callback.message, backend_url)
        else:
            # Если сообщение отсутствует (inline message), используем callback.answer с текстом
            logger.warning("Help callback received without message (inline message)")
            # Для inline сообщений используем callback.answer с show_alert
            await callback.answer(
                "Используйте команду /help в чате с ботом для получения инструкции",
                show_alert=True,
            )

    @router.message(F.document)
    async def document_handler(message: Message):
        await BotHandlers.handle_document(
            message, backend_url, bot_token, webapp_disabled, webapp_only
        )

    @router.message()
    async def any_message(message: Message):
        await BotHandlers.handle_web_app_data(message)

    dp.include_router(router)
