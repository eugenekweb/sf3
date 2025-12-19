import os


class Config:
    """Конфигурация Flask приложения"""

    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    UPLOAD_FOLDER = "/app/uploads"
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB максимальный размер файла
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    BACKEND_URL = os.getenv("BACKEND_URL", "")
    WEBAPP_DISABLED = os.getenv("WEBAPP_DISABLED", "False").lower() == "true"
    WEBAPP_ONLY = os.getenv("WEBAPP_ONLY", "False").lower() == "true"
    VERBOSE_LOGGING = os.getenv("VERBOSE_LOGGING", "False").lower() == "true"

    # Таймауты (в секундах)
    UPLOAD_TIMEOUT = int(os.getenv("UPLOAD_TIMEOUT", "300"))  # 5 минут
    PROCESSING_TIMEOUT = int(os.getenv("PROCESSING_TIMEOUT", "1800"))  # 30 минут
    CHUNK_TIMEOUT = int(os.getenv("CHUNK_TIMEOUT", "300"))  # 5 минут на чанк
    MESSAGE_TIMEOUT = int(os.getenv("MESSAGE_TIMEOUT", "30"))  # 30 секунд для текстовых сообщений
    CHUNK_EXPIRY_HOURS = int(os.getenv("CHUNK_EXPIRY_HOURS", "24"))  # Время жизни чанков в часах

    # Пороги и лимиты
    EXCEL_THRESHOLD = int(os.getenv("EXCEL_THRESHOLD", "50"))  # Порог для Excel/текст
    MAX_FILES = int(os.getenv("MAX_FILES", "10"))
    # Размер чанка в байтах (10 МБ)
    CHUNK_SIZE_ENV = os.getenv("CHUNK_SIZE", str(10 * 1024 * 1024))
    try:
        CHUNK_SIZE = int(CHUNK_SIZE_ENV)
    except (TypeError, ValueError):
        raise ValueError(
            f"Invalid CHUNK_SIZE value: {CHUNK_SIZE_ENV!r}. It must be an integer number of bytes."
        )
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))  # Максимум попыток загрузки чанка
    
    # Порог уверенности для определения кодировки (0.0-1.0)
    ENCODING_CONFIDENCE_THRESHOLD = float(os.getenv("ENCODING_CONFIDENCE_THRESHOLD", "0.8"))

    @property
    def TELEGRAM_API_URL(self):
        """URL Telegram API"""
        if self.BOT_TOKEN:
            return f"https://api.telegram.org/bot{self.BOT_TOKEN}"
        return None

    ALLOWED_EXTENSIONS = {"json"}


config = Config()


def allowed_file(filename):
    """Проверка расширения файла"""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXTENSIONS
    )
