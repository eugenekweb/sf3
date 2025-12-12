import logging
import os

logger = logging.getLogger(__name__)

def setup_logging():
    """Настройка логирования"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def get_env(key, default=None):
    """Безопасное получение переменных окружения"""
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"Environment variable {key} is required")
    return value

class Config:
    """Конфигурация приложения"""
    BOT_TOKEN = get_env("BOT_TOKEN")
    # Для WebApp нужен публичный URL (HTTPS), не внутренний Docker адрес
    # По умолчанию используем localhost для разработки
    BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5000")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    VERBOSE_LOGGING = os.getenv("VERBOSE_LOGGING", "False").lower() == "true"
    # Таймауты (в секундах)
    UPLOAD_TIMEOUT = int(os.getenv("UPLOAD_TIMEOUT", "300"))  # 5 минут
    # Настройки управления веб-апп
    WEBAPP_DISABLED = os.getenv("WEBAPP_DISABLED", "False").lower() == "true"
    WEBAPP_ONLY = os.getenv("WEBAPP_ONLY", "False").lower() == "true"

