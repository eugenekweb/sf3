"""Утилиты для обработки и отправки результатов"""
import logging
import time
from werkzeug.utils import secure_filename
from processors import ChatParser, FileGrouper
from excel_generator import ExcelGenerator
from telegram_sender import TelegramSender
from config import config

logger = logging.getLogger(__name__)


def process_and_send_results(file_data_list, user_id, combine_results=False):
    """
    Обработка файлов и отправка результатов пользователю
    
    Args:
        file_data_list: Список данных файлов
        user_id: ID пользователя
        combine_results: Объединить результаты в один файл
    
    Returns:
        dict: Результат обработки
    """
    if not config.BOT_TOKEN:
        return {"error": "BOT_TOKEN not configured"}, 500
    
    sender = TelegramSender(config.BOT_TOKEN)
    excel_gen = ExcelGenerator()
    parser = ChatParser()
    
    if combine_results:
        logger.info("Combine results flag is ON. Merging all files into one result.")
        parser.reset()
        all_messages = FileGrouper.merge_messages(file_data_list)
        parser.process_messages(all_messages)
        results = parser.get_results()
        
        participants = results['participants']
        mentions = results['mentions']
        channels = results['channels']
        total_participants = len(participants)
        mentions_with_username = [m for m in mentions if m.get('username')]
        mentions_count = len(mentions_with_username)
        
        excel_file = excel_gen.generate(participants, mentions, channels, "Combined result")
        filename = f"combined-export-{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
        caption = (
            f"📊 Сводный экспорт участников\n\n"
            f"✅ Обработка завершена!\n\n"
            f"💬 Файлы: {len(file_data_list)}\n"
            f"👤 Участников: {total_participants}\n"
            f"👥 Упоминаний: {mentions_count}"
        )
        sender.send_document(user_id, excel_file, filename, caption=caption)
        time.sleep(0.5)
        groups_count = 1
    else:
        groups = FileGrouper.group_files(file_data_list)
        groups_count = len(groups)
        
        for chat_key, chat_files in groups.items():
            chat_name = chat_key[0] or "Unknown"
            logger.info(f"Processing chat: {chat_name} ({len(chat_files)} files)")
            
            all_messages = FileGrouper.merge_messages(chat_files)
            parser.reset()
            parser.process_messages(all_messages)
            results = parser.get_results()
            
            participants = results['participants']
            mentions = results['mentions']
            channels = results['channels']
            total_participants = len(participants)
            
            logger.info(f"Chat {chat_name}: {total_participants} participants, {len(mentions)} mentions, {len(channels)} channels")
            
            if total_participants == 0:
                sender.send_message(
                    user_id,
                    f"⚠️ В чате {chat_name} не найдено участников.",
                    parse_mode="Markdown"
                )
                time.sleep(0.5)
                continue
            
            if total_participants < config.EXCEL_THRESHOLD:
                text_list = excel_gen.generate_text_list(participants, mentions, channels, chat_name)
                sender.send_message(user_id, text_list, parse_mode="Markdown")
                time.sleep(0.5)
            else:
                excel_file = excel_gen.generate(participants, mentions, channels, chat_name)
                # Обрабатываем имя чата для безопасного имени файла
                if chat_name and chat_name != "Unknown":
                    safe_chat_name = secure_filename(chat_name).replace(' ', '_').strip('_')
                    # Если secure_filename вернул пустую строку, используем исходное имя с очисткой
                    if not safe_chat_name:
                        safe_chat_name = "".join(c for c in chat_name if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
                        if not safe_chat_name:
                            safe_chat_name = "chat"
                else:
                    safe_chat_name = "chat"
                # Всегда добавляем дату в имя файла
                filename = f"{safe_chat_name}_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
                mentions_with_username = [m for m in mentions if m.get('username')]
                mentions_count = len(mentions_with_username)
                caption = (
                    f"📊 Экспорт участников чата: {chat_name}\n\n"
                    f"✅ Обработка завершена!\n\n"
                    f"💬 Чат: {chat_name}\n"
                    f"👤 Участников: {total_participants}\n"
                    f"👥 Упоминаний: {mentions_count}"
                )
                sender.send_document(user_id, excel_file, filename, caption=caption)
                time.sleep(0.5)
    
    return {"groups_count": groups_count}


def send_completion_message(user_id, total_files_processed, total_files_uploaded, failed_count=0):
    """
    Отправка сообщения о завершении обработки
    
    Args:
        user_id: ID пользователя
        total_files_processed: Количество обработанных файлов
        total_files_uploaded: Количество загруженных файлов
        failed_count: Количество файлов с ошибками
    """
    if not config.BOT_TOKEN:
        return
    
    sender = TelegramSender(config.BOT_TOKEN)
    
    if total_files_uploaded > 1 or failed_count > 0:
        time.sleep(0.5)
        if failed_count > 0:
            sender.send_message(
                user_id,
                f"✅ Обработано {total_files_processed} файл(а) из {total_files_uploaded}. Ошибки см. в сообщении выше.",
                parse_mode="Markdown"
            )
        else:
            sender.send_message(
                user_id,
                f"✅ Обработано {total_files_processed} файл(а) из {total_files_uploaded}.",
                parse_mode="Markdown"
            )


def send_keyboard_after_processing(user_id):
    """
    Отправка клавиатуры после обработки
    
    Args:
        user_id: ID пользователя
    """
    if not config.BOT_TOKEN:
        return
    
    sender = TelegramSender(config.BOT_TOKEN)
    time.sleep(0.5)
    
    if config.BACKEND_URL and config.BACKEND_URL.strip():
        webapp_url = config.BACKEND_URL.rstrip("/") + "/"
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "🚀 Загрузить и обработать",
                        "web_app": {"url": webapp_url}
                    }
                ],
                [
                    {
                        "text": "❓ Помощь",
                        "callback_data": "help"
                    }
                ]
            ]
        }
        sender.send_message_with_keyboard(
            user_id,
            "📤 *Хотите загрузить еще файлы?*\n\nНажмите кнопку ниже, чтобы открыть форму загрузки.",
            keyboard,
            parse_mode="Markdown"
        )
    elif config.BOT_TOKEN:
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "❓ Помощь",
                        "callback_data": "help"
                    }
                ]
            ]
        }
        sender.send_message_with_keyboard(
            user_id,
            "📤 *Обработка завершена!*\n\nДля загрузки файлов настройте BACKEND_URL в .env",
            keyboard,
            parse_mode="Markdown"
        )

