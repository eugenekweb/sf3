from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from config import config, allowed_file
import os
import logging
import shutil
import time
import json
from processors import ChatParser, FileGrouper
from excel_generator import ExcelGenerator
from telegram_sender import TelegramSender

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates')
app.config.from_object(config)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

if not os.path.exists(config.UPLOAD_FOLDER):
    os.makedirs(config.UPLOAD_FOLDER)

@app.route('/')
def index():
    """Главная страница с формой загрузки"""
    return render_template('index.html', debug_mode=config.DEBUG)

@app.route('/api/upload', methods=['POST'])
def upload():
    """API для загрузки и обработки файлов"""
    user_id = None
    temp_files = []
    combine_results = request.form.get('combine_results', 'false').lower() == 'true'
    
    try:
        user_id = request.form.get('user_id')
        if not user_id:
            if config.DEBUG:
                user_id = "123456789"
                logger.warning("DEBUG mode: using test user_id")
            else:
                return jsonify({"error": "user_id not provided"}), 400
        
        user_id = int(user_id)
        
        if 'files' not in request.files:
            return jsonify({"error": "No files provided"}), 400
        
        files = request.files.getlist('files')
        logger.info(f"Received {len(files)} file(s) for upload")
        
        if not files or all(not f.filename for f in files):
            return jsonify({"error": "No files selected"}), 400
        
        if len(files) > config.MAX_FILES:
            return jsonify({"error": f"Maximum {config.MAX_FILES} files allowed"}), 400
        
        parser = ChatParser()
        file_data_list = []
        failed_files = []
        
        for file in files:
            if not file or not file.filename:
                continue
            
            if not allowed_file(file.filename):
                failed_files.append({"name": file.filename, "error": "Неверное расширение файла"})
                continue
            
            filename = secure_filename(file.filename)
            temp_path = os.path.join(config.UPLOAD_FOLDER, f"temp_{os.urandom(8).hex()}_{filename}")
            
            try:
                with open(temp_path, 'wb') as f:
                    while True:
                        chunk = file.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                
                logger.info(f"File saved: {filename}, size: {os.path.getsize(temp_path) / 1024 / 1024:.2f} MB")
                temp_files.append(temp_path)
            except Exception as save_error:
                logger.error(f"Error saving file {filename}: {save_error}")
                failed_files.append({"name": filename, "error": f"Ошибка сохранения файла: {str(save_error)}"})
                continue
            
            try:
                file_data = parser.parse_file(temp_path)
                file_data['filepath'] = temp_path
                file_data_list.append(file_data)
            except Exception as e:
                logger.error(f"Error parsing file {filename}: {e}")
                failed_files.append({"name": filename, "error": str(e)})
                continue
        
        error_message_sent = False
        if failed_files and user_id and config.BOT_TOKEN:
            sender = TelegramSender(config.BOT_TOKEN)
            error_text = "❌ *Обнаружены проблемные файлы:*\n\n"
            for failed in failed_files:
                error_text += f"📄 *{failed['name']}*\n"
                error_text += f"   {failed['error']}\n\n"
            
            if len(files) > len(failed_files) and file_data_list:
                error_text += "Эти файлы были пропущены. Остальные файлы обрабатываются."
            
            sender.send_message(user_id, error_text, parse_mode="Markdown")
            error_message_sent = True
        
        if not file_data_list:
            if failed_files:
                if error_message_sent:
                    return jsonify({
                        "success": False,
                        "error": "Все файлы содержат ошибки. Проверьте сообщения выше.",
                        "failed_files": failed_files
                    }), 400
                else:
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
        
        if not config.BOT_TOKEN:
            return jsonify({"error": "BOT_TOKEN not configured"}), 500
        
        sender = TelegramSender(config.BOT_TOKEN)
        excel_gen = ExcelGenerator()
        
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
            mentions_count = len([m for m in mentions if m.get('username')])
            
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
        else:
            groups = FileGrouper.group_files(file_data_list)
            total_chats = len(groups)
            chat_index = 0
            
            for chat_key, chat_files in groups.items():
                chat_index += 1
                chat_name = chat_key[0] or "Unknown"
                logger.info(f"Processing chat: {chat_name} ({len(chat_files)} files)")
                
                all_messages = FileGrouper.merge_messages(chat_files)
                parser.reset()
                parser.process_messages(all_messages)
                results = parser.get_results()
                
                participants = results['participants']
                mentions = results['mentions']
                channels = results['channels']
                total_participants = results['total_participants']
                
                logger.info(f"Chat {chat_name}: {total_participants} participants, {len(mentions)} mentions, {len(channels)} channels")
                
                if total_participants < 50:
                    text_list = excel_gen.generate_text_list(participants, mentions, channels, chat_name)
                    sender.send_message(user_id, text_list, parse_mode="Markdown")
                    time.sleep(0.5)
                else:
                    excel_file = excel_gen.generate(participants, mentions, channels, chat_name)
                    safe_chat_name = secure_filename(chat_name).replace(' ', '_')
                    filename = f"{safe_chat_name}_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
                    mentions_count = len([m for m in mentions if m.get('username')])
                    caption = (
                        f"📊 Экспорт участников чата: {chat_name}\n\n"
                        f"✅ Обработка завершена!\n\n"
                        f"💬 Чат: {chat_name}\n"
                        f"👤 Участников: {total_participants}\n"
                        f"👥 Упоминаний: {mentions_count}"
                    )
                    sender.send_document(user_id, excel_file, filename, caption=caption)
                    time.sleep(0.5)
        
            total_files_processed = len(file_data_list)
            total_files_uploaded = len(files)
            failed_count = len(failed_files) if 'failed_files' in locals() else 0
            
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
        
        if combine_results:
            groups_count = 1
        else:
            groups_count = len(groups) if 'groups' in locals() else 0
        
        return jsonify({
            "success": True,
            "message": f"Обработано {len(file_data_list)} файл(ов), {groups_count} чат(ов)"
        })
    
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    
    finally:
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.info(f"Deleted temp file: {temp_file}")
            except Exception as e:
                logger.error(f"Error deleting temp file {temp_file}: {e}")

@app.route('/api/upload-chunk', methods=['POST'])
def upload_chunk():
    """API для загрузки одного чанка файла"""
    try:
        logger.info("Received upload-chunk request")
        
        # Получаем параметры
        upload_id = request.form.get('upload_id')
        chunk_index_str = request.form.get('chunk_index')
        total_chunks_str = request.form.get('total_chunks')
        filename = request.form.get('filename')
        file_size_str = request.form.get('file_size')
        user_id = request.form.get('user_id')
        
        logger.info(f"Parameters: upload_id={upload_id}, chunk_index={chunk_index_str}, filename={filename}, user_id={user_id}")
        
        if not upload_id or not filename or not user_id:
            logger.error("Missing required parameters")
            return jsonify({"success": False, "error": "Missing required parameters"}), 400
        
        try:
            chunk_index = int(chunk_index_str)
            total_chunks = int(total_chunks_str)
            file_size = int(file_size_str)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid numeric parameters: {e}")
            return jsonify({"success": False, "error": "Invalid numeric parameters"}), 400
        
        # Получаем чанк
        if 'chunk' not in request.files:
            logger.error("No chunk in request.files")
            return jsonify({"success": False, "error": "No chunk provided"}), 400
        
        chunk_file = request.files['chunk']
        if not chunk_file or not chunk_file.filename:
            logger.error("Invalid chunk file")
            return jsonify({"success": False, "error": "Invalid chunk"}), 400
        
        logger.info(f"Chunk file received: {chunk_file.filename}, size: {chunk_file.content_length} bytes")
        
        # Создаем директорию для чанков этого файла
        chunks_dir = os.path.join(config.UPLOAD_FOLDER, 'chunks', upload_id)
        os.makedirs(chunks_dir, exist_ok=True)
        
        # Сохраняем чанк
        chunk_path = os.path.join(chunks_dir, f'chunk_{chunk_index}.part')
        chunk_file.save(chunk_path)
        
        # Сохраняем метаданные файла (только при первом чанке)
        if chunk_index == 0:
            metadata = {
                'filename': filename,
                'file_size': file_size,
                'total_chunks': total_chunks,
                'user_id': user_id
            }
            metadata_path = os.path.join(chunks_dir, 'metadata.json')
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f)
        
        logger.info(f"Chunk {chunk_index + 1}/{total_chunks} saved for {filename} (upload_id: {upload_id})")
        
        return jsonify({
            "success": True,
            "message": f"Chunk {chunk_index + 1}/{total_chunks} uploaded",
            "upload_id": upload_id,
            "chunk_index": chunk_index
        })
    
    except Exception as e:
        logger.error(f"Error uploading chunk: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/complete-upload', methods=['POST'])
def complete_upload():
    """API для завершения загрузки: сборка файлов из чанков и обработка"""
    user_id = None
    temp_files = []
    chunks_dirs = []
    combine_results = request.form.get('combine_results', 'false').lower() == 'true'
    
    try:
        # Получаем user_id
        user_id = request.form.get('user_id')
        if not user_id:
            if config.DEBUG:
                user_id = "123456789"
                logger.warning("DEBUG mode: using test user_id")
            else:
                return jsonify({"success": False, "error": "user_id not provided"}), 400
        
        user_id = int(user_id)
        upload_ids = request.form.getlist('upload_ids[]')
        if not upload_ids:
            return jsonify({"success": False, "error": "No upload_ids provided"}), 400
        
        logger.info(f"Completing upload for {len(upload_ids)} file(s), user_id: {user_id}")
        
        parser = ChatParser()
        file_data_list = []
        failed_files = []
        
        for upload_id in upload_ids:
            chunks_dir = os.path.join(config.UPLOAD_FOLDER, 'chunks', upload_id)
            
            if not os.path.exists(chunks_dir):
                logger.error(f"Chunks directory not found: {chunks_dir}")
                failed_files.append({"name": upload_id, "error": "Чанки файла не найдены"})
                continue
            
            metadata_path = os.path.join(chunks_dir, 'metadata.json')
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                filename = metadata.get('filename', f"{upload_id}.json")
            else:
                filename = f"{upload_id}.json"
            
            chunk_files = []
            for f in os.listdir(chunks_dir):
                if f.startswith('chunk_') and f.endswith('.part'):
                    chunk_index = int(f.replace('chunk_', '').replace('.part', ''))
                    chunk_files.append((chunk_index, os.path.join(chunks_dir, f)))
            
            chunk_files.sort(key=lambda x: x[0])
            
            if not chunk_files:
                logger.error(f"No chunks found in {chunks_dir}")
                failed_files.append({"name": filename, "error": "Чанки не найдены"})
                continue
            
            temp_path = os.path.join(config.UPLOAD_FOLDER, f"temp_{os.urandom(8).hex()}_{secure_filename(filename)}")
            
            try:
                with open(temp_path, 'wb') as outfile:
                    for chunk_index, chunk_path in chunk_files:
                        with open(chunk_path, 'rb') as chunk_file:
                            shutil.copyfileobj(chunk_file, outfile)
                
                logger.info(f"File assembled: {filename}, size: {os.path.getsize(temp_path) / 1024 / 1024:.2f} MB")
                temp_files.append(temp_path)
                chunks_dirs.append(chunks_dir)
                
                try:
                    file_data = parser.parse_file(temp_path)
                    file_data['filepath'] = temp_path
                    file_data_list.append(file_data)
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Error parsing file {filename}: {e}")
                    failed_files.append({"name": filename, "error": error_msg})
                    continue
                    
            except Exception as e:
                logger.error(f"Error assembling file from chunks: {e}")
                failed_files.append({"name": filename, "error": f"Ошибка сборки файла: {str(e)}"})
                continue
        
        error_message_sent = False
        if failed_files and user_id and config.BOT_TOKEN:
            sender = TelegramSender(config.BOT_TOKEN)
            error_text = "❌ *Обнаружены проблемные файлы:*\n\n"
            for failed in failed_files:
                error_text += f"📄 *{failed['name']}*\n"
                error_text += f"   {failed['error']}\n\n"
            
            if len(upload_ids) > len(failed_files) and file_data_list:
                error_text += "Эти файлы были пропущены. Остальные файлы обрабатываются."
            
            sender.send_message(user_id, error_text, parse_mode="Markdown")
            error_message_sent = True
        
        if not file_data_list:
            if failed_files:
                if error_message_sent:
                    return jsonify({
                        "success": False,
                        "error": "Все файлы содержат ошибки. Проверьте сообщения выше.",
                        "failed_files": failed_files
                    }), 400
                else:
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
        
        sender = TelegramSender(config.BOT_TOKEN)
        excel_gen = ExcelGenerator()
        groups_count = 0
        
        if combine_results:
            logger.info("Combine results flag is ON. Merging all files into one result (complete_upload).")
            parser = ChatParser()
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
            groups_count = 1
            
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
        else:
            groups = FileGrouper.group_files(file_data_list)
            groups_count = len(groups)
            
            for chat_key, chat_files in groups.items():
                chat_name = chat_key[0] or "Unknown"
                logger.info(f"Processing chat: {chat_name} ({len(chat_files)} files)")
                
                parser = ChatParser()
                all_messages = FileGrouper.merge_messages(chat_files)
                parser.reset()
                parser.process_messages(all_messages)
                results = parser.get_results()
                
                participants = results['participants']
                mentions = results['mentions']
                channels = results['channels']
                total_participants = len(participants)
                
                if total_participants < 50:
                    text_list = excel_gen.generate_text_list(participants, mentions, channels, chat_name)
                    sender.send_message(user_id, text_list, parse_mode="Markdown")
                    time.sleep(0.5)
                else:
                    excel_file = excel_gen.generate(participants, mentions, channels, chat_name)
                    safe_chat_name = secure_filename(chat_name).replace(' ', '_')
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
        
            total_files_processed = len(file_data_list)
            total_files_uploaded = len(upload_ids)
            failed_count = len(failed_files) if 'failed_files' in locals() else 0
            
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
        
        time.sleep(2)
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
                "📤 Хотите загрузить ещё файлы?\n\nНажмите кнопку ниже, чтобы открыть форму загрузки.",
                keyboard,
                parse_mode="HTML"
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
                "📤 Обработка завершена!\n\nДля загрузки файлов настройте BACKEND_URL в .env",
                keyboard,
                parse_mode="HTML"
            )
        
        return jsonify({
            "success": True,
            "message": f"Обработано {len(file_data_list)} файл(ов), {groups_count} чат(ов)"
        })
    
    except Exception as e:
        logger.error(f"Complete upload error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
    
    finally:
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.info(f"Deleted temp file: {temp_file}")
            except Exception as e:
                logger.error(f"Error deleting temp file {temp_file}: {e}")
        
        for chunks_dir in chunks_dirs:
            try:
                if os.path.exists(chunks_dir):
                    shutil.rmtree(chunks_dir)
                    logger.info(f"Deleted chunks directory: {chunks_dir}")
            except Exception as e:
                logger.error(f"Error deleting chunks directory {chunks_dir}: {e}")

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large (max 2GB)"}), 413

if __name__ == "__main__":
    logger.info("🌐 Web server started on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=config.DEBUG)

