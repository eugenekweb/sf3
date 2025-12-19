"""Утилиты для обработки и отправки результатов"""
import logging
import time
from datetime import datetime
from processors import ChatParser, FileGrouper
from excel_generator import ExcelGenerator
from telegram_sender import TelegramSender
from config import config
from file_utils import sanitize_filename

logger = logging.getLogger(__name__)


def process_and_send_results(file_data_list, user_id, combine_results=False):
    """
    Обработка файлов и отправка результатов пользователю
    
    Args:
        file_data_list: Список данных файлов
        user_id: ID пользователя
        combine_results: Объединить результаты в один файл
    
    Returns:
        dict: Результат обработки. При ошибке содержит ключ "error", при успехе - "groups_count"
    """
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN not configured")
        return {"error": "BOT_TOKEN not configured", "groups_count": 0}
    
    sender = TelegramSender(config.BOT_TOKEN)
    excel_gen = ExcelGenerator()
    parser = ChatParser()
    
    # Общая дедупликация файлов по filepath (защита от повторной обработки)
    seen_filepaths = set()
    unique_file_data_list = []
    for file_data in file_data_list:
        filepath = file_data.get('filepath')
        if filepath and filepath not in seen_filepaths:
            seen_filepaths.add(filepath)
            unique_file_data_list.append(file_data)
        elif not filepath:
            unique_file_data_list.append(file_data)
    
    if combine_results:
        logger.info(f"Combine results flag is ON. Merging all {len(unique_file_data_list)} files into one result.")
        parser.reset()
        all_messages = FileGrouper.merge_messages(unique_file_data_list)
        parser.process_messages(all_messages)
        results = parser.get_results()
        
        participants = results['participants']
        mentions = results['mentions']
        channels = results['channels']
        total_participants = len(participants)
        mentions_with_username = [m for m in mentions if m.get('username')]
        mentions_count = len(mentions_with_username)
        channels_count = len(channels)
        
        # Проверка: есть ли хоть какие-то данные?
        if total_participants == 0 and mentions_count == 0 and channels_count == 0:
            sender.send_message(
                user_id,
                "⚠️ В объединенных файлах не найдено участников, упоминаний или каналов.",
                parse_mode="Markdown"
            )
            return {"groups_count": 0}
        
        # Проверяем порог для Excel/текст (как в необъединенном пути)
        if total_participants < config.EXCEL_THRESHOLD:
            text_list = excel_gen.generate_text_list(participants, mentions, channels, "Combined result")
            sender.send_message(user_id, text_list, parse_mode="HTML")
            time.sleep(0.5)
        else:
            excel_file = excel_gen.generate(participants, mentions, channels, "Combined result")
            filename = f"combined-export-{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            caption = (
                f"📊 Сводный экспорт участников\n\n"
                f"✅ Обработка завершена!\n\n"
                f"💬 Файлы: {len(unique_file_data_list)}\n"
                f"👤 Участников: {total_participants}\n"
                f"👥 Упоминаний: {mentions_count}"
            )
            if channels_count > 0:
                caption += f"\n📢 Каналов: {channels_count}"
            sender.send_document(user_id, excel_file, filename, caption=caption)
            time.sleep(0.5)
        groups_count = 1
    else:
        groups = FileGrouper.group_files(unique_file_data_list)
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
            mentions_with_username = [m for m in mentions if m.get('username')]
            mentions_count = len(mentions_with_username)
            channels_count = len(channels)
            
            logger.info(f"Chat {chat_name}: {total_participants} participants, {len(mentions)} mentions, {channels_count} channels")
            
            # Проверка: есть ли хоть какие-то данные? (согласовано с combined mode)
            if total_participants == 0 and mentions_count == 0 and channels_count == 0:
                sender.send_message(
                    user_id,
                    f"⚠️ В чате {chat_name} не найдено участников, упоминаний или каналов.",
                    parse_mode="Markdown"
                )
                time.sleep(0.5)
                continue
            
            if total_participants < config.EXCEL_THRESHOLD:
                text_list = excel_gen.generate_text_list(participants, mentions, channels, chat_name)
                sender.send_message(user_id, text_list, parse_mode="HTML")
                time.sleep(0.5)
            else:
                excel_file = excel_gen.generate(participants, mentions, channels, chat_name)
                
                # 1. Очищаем только имя чата (кириллица теперь сохраняется)
                safe_chat_name = sanitize_filename(chat_name, default="chat")
                
                # 2. Формируем метку времени (теперь через f-строку отдельно для надежности)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # 3. Собираем финальное имя: префикс + очищенное имя + время + расширение
                filename = f"chat_export_{safe_chat_name}_{timestamp}.xlsx"
                
                logger.info(f"Processing chat finished. Filename generated: {filename}")
                
                # mentions_with_username и mentions_count уже определены выше (строка 106-107)
                caption = (
                    f"📊 Экспорт участников чата: {chat_name}\n\n"
                    f"✅ Обработка завершена!\n\n"
                    f"💬 Чат: {chat_name}\n"
                    f"👤 Участников: {total_participants}\n"
                    f"👥 Упоминаний: {mentions_count}"
                )
                if channels_count > 0:
                    caption += f"\n📢 Каналов: {channels_count}"
                sender.send_document(user_id, excel_file, filename, caption=caption)
                time.sleep(0.5)
    
    return {"groups_count": groups_count}


def send_completion_message(user_id, total_files_processed, total_files_uploaded, failed_count=0, error_message_sent=False):
    """
    Отправка сообщения о завершении обработки
    
    Args:
        user_id: ID пользователя
        total_files_processed: Количество обработанных файлов
        total_files_uploaded: Количество загруженных файлов
        failed_count: Количество файлов с ошибками
        error_message_sent: Флаг, указывающий, что сообщение об ошибках уже было отправлено
    """
    if not config.BOT_TOKEN:
        return
    
    sender = TelegramSender(config.BOT_TOKEN)
    
    # Отправляем сообщение о завершении для любого количества файлов
    time.sleep(0.5)
    
    # Переструктурируем логику: сначала проверяем error_message_sent, затем failed_count
    if error_message_sent:
        # Ошибки уже были отправлены ранее - отправляем сообщение о завершении с упоминанием ошибок
        sender.send_message(
            user_id,
            f"✅ Обработано {total_files_processed} файл(а) из {total_files_uploaded}. Ошибки см. в сообщении выше.",
            parse_mode="Markdown"
        )
    elif failed_count > 0:
        # Есть ошибки, но они не были отправлены (например, из-за отсутствия BOT_TOKEN или user_id)
        # Не упоминаем "сообщение выше", так как его нет
        sender.send_message(
            user_id,
            f"✅ Обработано {total_files_processed} файл(а) из {total_files_uploaded}. Некоторые файлы не удалось обработать.",
            parse_mode="Markdown"
        )
    else:
        # Нет ошибок - отправляем обычное сообщение о завершении
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

