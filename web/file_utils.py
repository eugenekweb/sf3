"""Утилиты для обработки файлов и валидации"""
import logging
from flask import jsonify

logger = logging.getLogger(__name__)


def validate_user_id(user_id_str, debug_mode=False):
    """
    Валидация user_id
    
    Args:
        user_id_str: Строка с user_id
        debug_mode: Режим отладки
    
    Returns:
        tuple: (user_id: int, error_response: dict or None)
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
        return user_id, None
    except (ValueError, TypeError):
        return None, jsonify({"error": "Invalid user_id format"}), 400

