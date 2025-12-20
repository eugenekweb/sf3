"""Утилиты для обработки файлов и валидации"""

import logging
import re
from flask import jsonify
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)


def validate_user_id(user_id_str, debug_mode=False):
    """
    Валидация user_id

    Args:
        user_id_str: Строка с user_id
        debug_mode: Режим отладки

    Returns:
        tuple: (user_id: int or None, error_response: dict or None, status_code: int or None)
    """
    if not user_id_str:
        return None, jsonify({"error": "user_id not provided"}), 400

    try:
        user_id = int(user_id_str)
        if user_id <= 0:
            return None, jsonify({"error": "Invalid user_id"}), 400
        return user_id, None, None
    except (ValueError, TypeError):
        return None, jsonify({"error": "Invalid user_id format"}), 400


def _transliterate_ru(text):
    """
    Простая транслитерация русских букв в латиницу
    
    Args:
        text: Текст с кириллицей
    
    Returns:
        str: Текст с транслитерированными русскими буквами
    """
    ru_en = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        # Заглавные
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
        'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
        'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
    }
    return ''.join(ru_en.get(c, c) for c in text)


def validate_upload_id(upload_id):
    """
    Валидация upload_id для предотвращения path traversal атак
    
    Args:
        upload_id: Идентификатор загрузки от клиента
    
    Returns:
        tuple: (is_valid: bool, sanitized_id: str or None, error_message: str or None)
    """
    if not upload_id:
        return False, None, "upload_id is required"
    
    # Проверяем на path traversal последовательности
    if '..' in upload_id or '/' in upload_id or '\\' in upload_id:
        return False, None, "upload_id contains invalid characters"
    
    # Разрешаем только alphanumeric, дефисы и подчеркивания
    # UUID формат: 8-4-4-4-12 (например: 550e8400-e29b-41d4-a716-446655440000)
    if not re.match(r'^[a-zA-Z0-9_-]+$', upload_id):
        return False, None, "upload_id contains invalid characters"
    
    # Дополнительная проверка: не должен быть слишком длинным (UUID обычно 36 символов)
    if len(upload_id) > 128:
        return False, None, "upload_id is too long"
    
    return True, upload_id, None


def sanitize_filename(chat_name, default="chat"):
    """
    Ультимативно простая очистка имени файла.
    Удаляем только системно запрещенные символы.
    """
    if not chat_name or not isinstance(chat_name, str):
        return default
    
    # 1. Оставляем только буквы, цифры, пробелы, дефисы и точки
    # Используем простой список разрешенных символов для надежности
    cleaned = ""
    # Запрещенные в Windows/Linux символы: / \ : * ? " < > |
    forbidden = r'/\?%*:|"<>'
    
    for char in chat_name:
        if char not in forbidden and ord(char) > 31:
            cleaned += char
        else:
            cleaned += "_"
            
    # 2. Заменяем пробелы на подчеркивания
    cleaned = cleaned.replace(" ", "_")
    
    # 3. Схлопываем подчеркивания
    cleaned = re.sub(r"_+", "_", cleaned)
    
    # 4. Финальная очистка краев
    result = cleaned.strip("_-. ")
    
    return result if result else default
