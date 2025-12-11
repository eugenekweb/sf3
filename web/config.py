import os

class Config:
    """Конфигурация Flask приложения"""
    DEBUG = os.getenv("DEBUG", "False") == "True"
    UPLOAD_FOLDER = "/app/uploads"
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2 ГБ
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    @property
    def TELEGRAM_API_URL(self):
        """URL Telegram API"""
        if self.BOT_TOKEN:
            return f"https://api.telegram.org/bot{self.BOT_TOKEN}"
        return None
    
    ALLOWED_EXTENSIONS = {'json'}
    MAX_FILES = 10

config = Config()

def allowed_file(filename):
    """Проверка расширения файла"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in config.ALLOWED_EXTENSIONS

