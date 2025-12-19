"""Утилиты для обработки файлов и валидации"""

import logging
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
        if debug_mode:
            user_id_str = "123456789"
            logger.warning("DEBUG mode: using test user_id")
        else:
            return None, jsonify({"error": "user_id not provided"}), 400

    try:
        user_id = int(user_id_str)
        if user_id <= 0:
            return None, jsonify({"error": "Invalid user_id"}), 400
        return user_id, None, None
    except (ValueError, TypeError):
        return None, jsonify({"error": "Invalid user_id format"}), 400


def sanitize_filename(chat_name, default="chat"):
    """
    Санитизация имени чата для безопасного имени файла

    Args:
        chat_name: Исходное имя чата
        default: Значение по умолчанию, если имя не удалось обработать

    Returns:
        str: Безопасное имя файла
    """
    # Проверяем на пустое значение и известные значения "неизвестного чата"
    # (поддерживаем оба варианта для обратной совместимости)
    if not chat_name or chat_name in ("Unknown", "Неизвестный чат"):
        return default

    # Пробуем secure_filename
    safe_chat_name = secure_filename(chat_name).replace(" ", "_").strip("_")

    # Если secure_filename вернул пустую строку, используем исходное имя с очисткой
    if not safe_chat_name:
        safe_chat_name = (
            "".join(c for c in chat_name if c.isalnum() or c in (" ", "-", "_"))
            .strip()
            .replace(" ", "_")
        )

        if not safe_chat_name:
            safe_chat_name = default

    return safe_chat_name
