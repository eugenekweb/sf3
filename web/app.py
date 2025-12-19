from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from config import config, allowed_file
import os
import logging
import shutil
import json
from datetime import datetime, timedelta
from processors import ChatParser, FileGrouper
from telegram_sender import TelegramSender
from file_utils import validate_user_id, validate_upload_id
from result_processor import process_and_send_results, send_completion_message, send_keyboard_after_processing

# Настройка логирования: интегрируемся с Gunicorn или настраиваем дефолтный вывод
if __name__ != '__main__':
    # Если запущены под Gunicorn, используем его настройки для всех логгеров
    gunicorn_logger = logging.getLogger('gunicorn.error')
    root_logger = logging.getLogger()
    # Убираем лишние обработчики, если они уже есть, чтобы не было двойного логирования
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.handlers = gunicorn_logger.handlers
    root_logger.setLevel(gunicorn_logger.level)
    logger = logging.getLogger(__name__)
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates')
app.config.from_object(config)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

if not os.path.exists(config.UPLOAD_FOLDER):
    os.makedirs(config.UPLOAD_FOLDER)


def _cleanup_old_chunks():
    """
    Очистка старых директорий с чанками, которые не были собраны в файлы.
    Удаляет директории старше CHUNK_EXPIRY_HOURS часов.
    """
    chunks_base_dir = os.path.join(config.UPLOAD_FOLDER, 'chunks')
    if not os.path.exists(chunks_base_dir):
        return
    
    expiry_time = datetime.now() - timedelta(hours=config.CHUNK_EXPIRY_HOURS)
    deleted_count = 0
    
    try:
        for upload_id_dir in os.listdir(chunks_base_dir):
            upload_id_path = os.path.join(chunks_base_dir, upload_id_dir)
            if not os.path.isdir(upload_id_path):
                continue
            
            # Проверяем время модификации директории или метаданных
            metadata_path = os.path.join(upload_id_path, 'metadata.json')
            if os.path.exists(metadata_path):
                # Используем время модификации метаданных
                mtime = datetime.fromtimestamp(os.path.getmtime(metadata_path))
            else:
                # Используем время модификации директории
                mtime = datetime.fromtimestamp(os.path.getmtime(upload_id_path))
            
            if mtime < expiry_time:
                try:
                    shutil.rmtree(upload_id_path)
                    deleted_count += 1
                    logger.info(f"Deleted old chunks directory: {upload_id_path} (age: {datetime.now() - mtime})")
                except Exception as e:
                    logger.error(f"Error deleting old chunks directory {upload_id_path}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old chunk directory(ies)")
    except Exception as e:
        logger.error(f"Error during chunks cleanup: {e}")


@app.route('/')
def index():
    """Главная страница с формой загрузки"""
    return render_template('index.html', 
                         debug_mode=config.DEBUG,
                         chunk_size=config.CHUNK_SIZE,
                         max_retries=config.MAX_RETRIES)

@app.route('/api/upload', methods=['POST'])
def upload():
    """API для загрузки и обработки файлов"""
    user_id = None
    temp_files = []
    combine_results = request.form.get('combine_results', 'false').lower() == 'true'
    
    try:
        user_id_str = request.form.get('user_id')
        user_id, error_response, status_code = validate_user_id(user_id_str, config.DEBUG)
        if error_response:
            return error_response, status_code
        
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
            
            # Добавляем путь в список для очистки ДО операций, которые могут упасть
            temp_files.append(temp_path)
            
            try:
                with open(temp_path, 'wb') as f:
                    while True:
                        chunk = file.read(config.CHUNK_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                
                logger.info(f"File saved: {filename}, size: {os.path.getsize(temp_path) / 1024 / 1024:.2f} MB")
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
        
        # Обработка и отправка результатов
        result = process_and_send_results(file_data_list, user_id, combine_results)
        if "error" in result:
            logger.error(f"Error in process_and_send_results: {result['error']}")
            return jsonify(result), 500
        
        groups_count = result.get("groups_count", 0)
        
        # Отправка сообщения о завершении
        total_files_processed = len(file_data_list)
        total_files_uploaded = len(files)
        failed_count = len(failed_files) if 'failed_files' in locals() else 0
        send_completion_message(user_id, total_files_processed, total_files_uploaded, failed_count, error_message_sent)
        
        # Отправка клавиатуры
        send_keyboard_after_processing(user_id)
        
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
        
        # Валидация upload_id для предотвращения path traversal
        is_valid, sanitized_upload_id, error_msg = validate_upload_id(upload_id)
        if not is_valid:
            logger.error(f"Invalid upload_id: {error_msg}")
            return jsonify({"success": False, "error": f"Invalid upload_id: {error_msg}"}), 400
        upload_id = sanitized_upload_id
        
        # Создаем директорию для чанков этого файла
        chunks_dir = os.path.join(config.UPLOAD_FOLDER, 'chunks', upload_id)
        os.makedirs(chunks_dir, exist_ok=True)
        
        # Очистка старых чанков при загрузке нового
        _cleanup_old_chunks()
        
        # Сохраняем чанк
        chunk_path = os.path.join(chunks_dir, f'chunk_{chunk_index}.part')
        chunk_file.save(chunk_path)
        
        # Сохраняем метаданные файла при первом запросе (любом чанке)
        # Используем атомарную проверку и создание файла для предотвращения Race Condition
        metadata_path = os.path.join(chunks_dir, 'metadata.json')
        if not os.path.exists(metadata_path):
            metadata = {
                'filename': filename,
                'file_size': file_size,
                'total_chunks': total_chunks,
                'user_id': user_id
            }
            try:
                # Пытаемся создать файл атомарно. Если он уже существует, os.open выбросит FileExistsError
                fd = os.open(metadata_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f)
                logger.info(f"Metadata created for upload_id {upload_id} on chunk {chunk_index}")
            except FileExistsError:
                # Метаданные уже созданы другим параллельным запросом, это нормально
                logger.debug(f"Metadata already exists for upload_id {upload_id}")
            except Exception as e:
                logger.error(f"Error creating metadata for {upload_id}: {e}")
        
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
        # Получаем и валидируем user_id
        user_id_str = request.form.get('user_id')
        user_id, error_response, status_code = validate_user_id(user_id_str, config.DEBUG)
        if error_response:
            return error_response, status_code
        upload_ids = request.form.getlist('upload_ids[]')
        if not upload_ids:
            return jsonify({"success": False, "error": "No upload_ids provided"}), 400
        
        logger.info(f"Completing upload for {len(upload_ids)} file(s), user_id: {user_id}")
        
        parser = ChatParser()
        file_data_list = []
        failed_files = []
        
        for upload_id in upload_ids:
            # Валидация upload_id для предотвращения path traversal
            is_valid, sanitized_upload_id, error_msg = validate_upload_id(upload_id)
            if not is_valid:
                logger.error(f"Invalid upload_id: {error_msg}")
                failed_files.append({"name": upload_id, "error": f"Неверный идентификатор загрузки: {error_msg}"})
                continue
            upload_id = sanitized_upload_id
            
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
                
                # Проверка принадлежности upload_id пользователю (защита от IDOR)
                metadata_user_id = metadata.get('user_id')
                # Явно проверяем наличие user_id в метаданных (отклоняем, если отсутствует)
                if metadata_user_id is None:
                    logger.warning(
                        f"Missing user_id in metadata for upload_id {upload_id}. "
                        f"Rejecting for security."
                    )
                    failed_files.append({
                        "name": filename,
                        "error": "Метаданные файла повреждены: отсутствует идентификатор пользователя"
                    })
                    continue
                # Проверяем соответствие user_id
                if str(metadata_user_id) != str(user_id):
                    logger.warning(
                        f"User ID mismatch for upload_id {upload_id}: "
                        f"requested {user_id}, but metadata has {metadata_user_id}"
                    )
                    failed_files.append({
                        "name": filename,
                        "error": "Доступ запрещен: файл принадлежит другому пользователю"
                    })
                    continue
            else:
                filename = f"{upload_id}.json"
                # Если metadata.json отсутствует, пропускаем файл для безопасности
                logger.warning(f"Metadata not found for upload_id {upload_id}, skipping for security")
                failed_files.append({
                    "name": filename,
                    "error": "Метаданные файла не найдены"
                })
                continue
            
            chunk_files = []
            for f in os.listdir(chunks_dir):
                if f.startswith('chunk_') and f.endswith('.part'):
                    try:
                        chunk_index = int(f.replace('chunk_', '').replace('.part', ''))
                        chunk_files.append((chunk_index, os.path.join(chunks_dir, f)))
                    except ValueError:
                        logger.warning(f"Skipping malformed chunk file: {f} in {chunks_dir}")
                        continue
            
            chunk_files.sort(key=lambda x: x[0])
            
            if not chunk_files:
                logger.error(f"No chunks found in {chunks_dir}")
                failed_files.append({"name": filename, "error": "Чанки не найдены"})
                continue
            
            temp_path = os.path.join(config.UPLOAD_FOLDER, f"temp_{os.urandom(8).hex()}_{secure_filename(filename)}")
            
            # Добавляем ресурсы в списки для очистки ДО операций, которые могут упасть
            temp_files.append(temp_path)
            chunks_dirs.append(chunks_dir)
            
            try:
                with open(temp_path, 'wb') as outfile:
                    for chunk_index, chunk_path in chunk_files:
                        with open(chunk_path, 'rb') as chunk_file:
                            shutil.copyfileobj(chunk_file, outfile)
                
                # Проверка размера собранного файла против метаданных
                actual_size = os.path.getsize(temp_path)
                expected_size = metadata.get('file_size')
                if expected_size is not None and actual_size != expected_size:
                    error_msg = (
                        f"Несоответствие размера файла: ожидалось {expected_size} байт, "
                        f"получено {actual_size} байт. Файл может быть поврежден или неполон."
                    )
                    logger.error(f"File size mismatch for {filename}: {error_msg}")
                    failed_files.append({"name": filename, "error": error_msg})
                    continue
                
                logger.info(f"File assembled: {filename}, size: {actual_size / 1024 / 1024:.2f} MB")
                
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
        
        if not config.BOT_TOKEN:
            return jsonify({"success": False, "error": "BOT_TOKEN not configured"}), 500
        
        # Обработка и отправка результатов
        result = process_and_send_results(file_data_list, user_id, combine_results)
        if "error" in result:
            logger.error(f"Error in process_and_send_results: {result['error']}")
            return jsonify({"success": False, **result}), 500
        
        groups_count = result.get("groups_count", 0)
        
        # Отправка сообщения о завершении
        total_files_processed = len(file_data_list)
        total_files_uploaded = len(upload_ids)
        failed_count = len(failed_files) if 'failed_files' in locals() else 0
        send_completion_message(user_id, total_files_processed, total_files_uploaded, failed_count, error_message_sent)
        
        # Отправка клавиатуры
        send_keyboard_after_processing(user_id)
        
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

