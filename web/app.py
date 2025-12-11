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

if not os.path.exists(config.UPLOAD_FOLDER):
    os.makedirs(config.UPLOAD_FOLDER)

@app.route('/')
def index():
    """Главная страница с формой загрузки"""
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload():
    """API для загрузки и обработки файлов"""
    user_id = None
    temp_files = []
    
    try:
        # Получаем user_id
        user_id = request.form.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id not provided"}), 400
        
        user_id = int(user_id)
        
        # Проверяем наличие файлов
        if 'files' not in request.files:
            return jsonify({"error": "No files provided"}), 400
        
        files = request.files.getlist('files')
        
        if not files or all(not f.filename for f in files):
            return jsonify({"error": "No files selected"}), 400
        
        # Проверка количества файлов
        if len(files) > config.MAX_FILES:
            return jsonify({"error": f"Maximum {config.MAX_FILES} files allowed"}), 400
        
        # Сохранение файлов во временную директорию
        parser = ChatParser()
        file_data_list = []
        
        for file in files:
            if not file or not file.filename:
                continue
            
            if not allowed_file(file.filename):
                logger.warning(f"File {file.filename} has invalid extension")
                continue
            
            # Сохраняем во временный файл
            filename = secure_filename(file.filename)
            temp_path = os.path.join(config.UPLOAD_FOLDER, f"temp_{os.urandom(8).hex()}_{filename}")
            file.save(temp_path)
            temp_files.append(temp_path)
            
            try:
                # Парсим файл
                file_data = parser.parse_file(temp_path)
                file_data['filepath'] = temp_path
                file_data_list.append(file_data)
            except Exception as e:
                logger.error(f"Error parsing file {filename}: {e}")
                continue
        
        if not file_data_list:
            return jsonify({"error": "No valid files to process"}), 400
        
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
            
            # Отбивка между чатами (кроме первого)
            if chat_index > 1:
                sender.send_message(user_id, "━━━━━━━━━━━━━━━━━━━━")
                time.sleep(0.3)
            
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
                sender.send_message(user_id, text_list)
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
        
        # Финальное сообщение только если обработано больше одного чата
        if total_chats > 1:
            time.sleep(0.5)
            sender.send_message(
                user_id,
                f"✅ <b>Все чаты обработаны!</b>\n\n"
                f"📊 Обработано: {total_chats} чат(ов)"
            )
        
        return jsonify({
            "success": True,
            "message": f"Обработано {len(file_data_list)} файл(ов), {len(groups)} чат(ов)"
        })
    
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        if user_id and config.BOT_TOKEN:
            try:
                sender = TelegramSender(config.BOT_TOKEN)
                sender.send_error(user_id, str(e))
            except Exception as send_err:
                logger.error(f"Failed to send error message: {send_err}")
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

