from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from config import config, allowed_file
import os
import logging
from processors import ChatParser, FileGrouper
from excel_generator import ExcelGenerator
from telegram_sender import TelegramSender

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates')
app.config.from_object(config)
# Увеличиваем лимиты для больших файлов
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2 ГБ
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

if not os.path.exists(config.UPLOAD_FOLDER):
    os.makedirs(config.UPLOAD_FOLDER)

@app.route('/')
def index():
    """Главная страница с формой загрузки"""
    # Логируем значение DEBUG для диагностики
    logger.info(f"DEBUG mode: {config.DEBUG}")
    return render_template('index.html', debug_mode=config.DEBUG)

@app.route('/api/upload', methods=['POST'])
def upload():
    """API для загрузки и обработки файлов"""
    user_id = None
    temp_files = []
    
    # Логируем начало загрузки
    content_length = request.content_length or 0
    content_length_mb = content_length / 1024 / 1024
    logger.info(f"Upload request started, content-length: {content_length_mb:.2f} MB, method: {request.method}, content-type: {request.content_type}")
    
    try:
        # Получаем user_id
        user_id = request.form.get('user_id')
        if not user_id:
            # В режиме DEBUG разрешаем работу без user_id (для тестирования)
            if config.DEBUG:
                user_id = "123456789"  # Тестовый ID для отладки
                logger.warning("DEBUG mode: using test user_id")
            else:
                return jsonify({"error": "user_id not provided"}), 400
        
        user_id = int(user_id)
        
        # Проверяем наличие файлов
        if 'files' not in request.files:
            logger.warning("No files in request")
            return jsonify({"error": "No files provided"}), 400
        
        files = request.files.getlist('files')
        logger.info(f"Received {len(files)} file(s) for upload")
        
        if not files or all(not f.filename for f in files):
            logger.warning("No valid filenames in request")
            return jsonify({"error": "No files selected"}), 400
        
        # Проверка количества файлов
        if len(files) > config.MAX_FILES:
            return jsonify({"error": f"Maximum {config.MAX_FILES} files allowed"}), 400
        
        # Сохранение файлов во временную директорию
        parser = ChatParser()
        file_data_list = []
        failed_files = []  # Список сломанных файлов
        
        for file in files:
            if not file or not file.filename:
                continue
            
            if not allowed_file(file.filename):
                logger.warning(f"File {file.filename} has invalid extension")
                failed_files.append({"name": file.filename, "error": "Неверное расширение файла"})
                continue
            
            # Сохраняем во временный файл
            filename = secure_filename(file.filename)
            temp_path = os.path.join(config.UPLOAD_FOLDER, f"temp_{os.urandom(8).hex()}_{filename}")
            
            # Сохраняем файл с обработкой больших файлов
            try:
                # Используем chunked чтение для больших файлов
                with open(temp_path, 'wb') as f:
                    while True:
                        chunk = file.read(8192)  # Читаем по 8KB
                        if not chunk:
                            break
                        f.write(chunk)
                
                # Проверяем, что файл сохранился
                saved_size = os.path.getsize(temp_path)
                logger.info(f"File saved: {filename}, size: {saved_size / 1024 / 1024:.2f} MB")
                temp_files.append(temp_path)
            except Exception as save_error:
                logger.error(f"Error saving file {filename}: {save_error}")
                failed_files.append({"name": filename, "error": f"Ошибка сохранения файла: {str(save_error)}"})
                continue
            
            try:
                # Парсим файл
                file_data = parser.parse_file(temp_path)
                file_data['filepath'] = temp_path
                file_data_list.append(file_data)
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error parsing file {filename}: {e}")
                failed_files.append({"name": filename, "error": error_msg})
                continue
        
        # Если есть сломанные файлы, отправляем информацию пользователю
        error_message_sent = False
        if failed_files and user_id and config.BOT_TOKEN:
            sender = TelegramSender(config.BOT_TOKEN)
            error_text = "❌ *Обнаружены проблемные файлы:*\n\n"
            for failed in failed_files:
                error_text += f"📄 *{failed['name']}*\n"
                error_text += f"   {failed['error']}\n\n"
            
            # Если файлов несколько и есть успешно обработанные - добавляем сообщение
            if len(files) > len(failed_files) and file_data_list:
                error_text += "Эти файлы были пропущены. Остальные файлы обрабатываются."
            # Если файл только один - не добавляем сообщение об остальных
            
            sender.send_message(user_id, error_text, parse_mode="Markdown")
            error_message_sent = True
        
        if not file_data_list:
            if failed_files:
                # Если уже отправили сообщение с деталями, возвращаем HTTP 400 с success: false
                # чтобы фронтенд правильно обработал ошибку
                if error_message_sent:
                    return jsonify({
                        "success": False,
                        "error": "Все файлы содержат ошибки. Проверьте сообщения выше.",
                        "failed_files": failed_files
                    }), 400  # Возвращаем 400, чтобы фронтенд обработал как ошибку
                else:
                    # Формируем сообщение об ошибке с именами файлов (если не отправили выше)
                    if len(failed_files) == 1:
                        error_msg = f"Файл {failed_files[0]['name']}: {failed_files[0]['error']}"
                    else:
                        file_names = ", ".join([f['name'] for f in failed_files])
                        error_msg = f"Все файлы содержат ошибки ({file_names})."
                    return jsonify({
                        "success": False,
                        "error": error_msg,
                        "failed_files": failed_files
                    }), 400
            return jsonify({
                "success": False,
                "error": "No valid files to process"
            }), 400
        
        # Группировка файлов по чатам
        groups = FileGrouper.group_files(file_data_list)
        
        # Проверка BOT_TOKEN
        if not config.BOT_TOKEN:
            return jsonify({"error": "BOT_TOKEN not configured"}), 500
        
        # Обработка каждого чата
        sender = TelegramSender(config.BOT_TOKEN)
        excel_gen = ExcelGenerator()
        
        import time
        total_chats = len(groups)
        chat_index = 0
        
        for chat_key, chat_files in groups.items():
            chat_index += 1
            chat_name = chat_key[0] or "Unknown"
            logger.info(f"Processing chat: {chat_name} ({len(chat_files)} files)")
            
            
            # Объединяем сообщения из всех файлов чата
            all_messages = FileGrouper.merge_messages(chat_files)
            
            # Парсим сообщения
            parser.reset()
            parser.process_messages(all_messages)
            results = parser.get_results()
            
            participants = results['participants']
            mentions = results['mentions']
            channels = results['channels']
            total_participants = results['total_participants']
            
            logger.info(f"Chat {chat_name}: {total_participants} participants, {len(mentions)} mentions, {len(channels)} channels")
            
            # Определяем формат результата
            if total_participants < 50:
                # Отправляем текстовый список с информацией об обработке
                text_list = excel_gen.generate_text_list(participants, mentions, channels, chat_name)
                # Используем Markdown для корректного отображения code блоков
                sender.send_message(user_id, text_list, parse_mode="Markdown")
                time.sleep(0.5)  # Задержка после текстового списка
            else:
                # Генерируем и отправляем Excel
                excel_file = excel_gen.generate(participants, mentions, channels, chat_name)
                filename = f"chat_export_{chat_name.replace(' ', '_')}.xlsx"
                # Добавляем информацию об обработке в caption (без HTML тегов)
                mentions_count = len([m for m in mentions if m.get('username')])
                caption = (
                    f"📊 Экспорт участников чата: {chat_name}\n\n"
                    f"✅ Обработка завершена!\n\n"
                    f"💬 Чат: {chat_name}\n"
                    f"👤 Участников: {total_participants}\n"
                    f"👥 Упоминаний: {mentions_count}"
                )
                sender.send_document(user_id, excel_file, filename, caption=caption)
                time.sleep(0.5)  # Задержка после отправки файла
        
        # Финальное сообщение с информацией об обработанных файлах
        total_files_processed = len(file_data_list)
        total_files_uploaded = len(files)  # Общее количество загруженных файлов в этом запросе
        failed_count = len(failed_files) if 'failed_files' in locals() else 0
        
        # Отправляем финальное сообщение только если было несколько файлов или есть ошибки
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
        
        # Отправляем кнопки загрузки и помощи после всех результатов (ВСЕГДА)
        time.sleep(0.5)
        logger.info(f"Preparing to send keyboard buttons. BACKEND_URL: {config.BACKEND_URL}, BOT_TOKEN: {'set' if config.BOT_TOKEN else 'not set'}")
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
            logger.info(f"Sending keyboard buttons to user {user_id}, BACKEND_URL: {config.BACKEND_URL}")
            result = sender.send_message_with_keyboard(
                user_id,
                "📤 *Хотите загрузить еще файлы?*\n\nНажмите кнопку ниже, чтобы открыть форму загрузки.",
                keyboard,
                parse_mode="Markdown"
            )
            if not result:
                logger.error(f"Failed to send keyboard buttons to user {user_id}")
        elif config.BOT_TOKEN:
            # Если BACKEND_URL не настроен, отправляем только кнопку помощи
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
        
        return jsonify({
            "success": True,
            "message": f"Обработано {len(file_data_list)} файл(ов), {len(groups)} чат(ов)"
        })
    
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        # Не отправляем сообщение об ошибке здесь, так как детальные ошибки уже отправлены выше
        # или будут отправлены через JSON response
        return jsonify({"error": str(e)}), 500
    
    finally:
        # Удаляем временные файлы
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.info(f"Deleted temp file: {temp_file}")
            except Exception as e:
                logger.error(f"Error deleting temp file {temp_file}: {e}")

@app.errorhandler(413)
def too_large(e):
    """Ошибка: файл слишком большой"""
    return jsonify({"error": "File too large (max 2GB)"}), 413

if __name__ == "__main__":
    logger.info("🌐 Web server started on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=config.DEBUG)

