import requests
import logging
from typing import Optional
from io import BytesIO
from config import config

logger = logging.getLogger(__name__)

class TelegramSender:
    """Отправка сообщений и файлов через Telegram Bot API"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(self, chat_id: int, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Отправка текстового сообщения
        
        Args:
            chat_id: ID чата пользователя
            text: Текст сообщения
            parse_mode: Режим парсинга (HTML или Markdown)
        
        Returns:
            bool: True если успешно, False иначе
        """
        try:
            url = f"{self.api_url}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            
            response = requests.post(url, json=data, timeout=config.MESSAGE_TIMEOUT)
            
            if response.status_code == 200:
                logger.info(f"Message sent to {chat_id}")
                return True
            else:
                logger.error(f"Failed to send message: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
    
    def send_document(self, chat_id: int, file_data: BytesIO, filename: str, 
                     caption: Optional[str] = None) -> bool:
        """
        Отправка файла (Excel)
        
        Args:
            chat_id: ID чата пользователя
            file_data: BytesIO поток с файлом
            filename: Имя файла
            caption: Подпись к файлу (опционально)
        
        Returns:
            bool: True если успешно, False иначе
        """
        try:
            url = f"{self.api_url}/sendDocument"
            
            file_data.seek(0)
            files = {
                'document': (filename, file_data, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            }
            
            data = {
                'chat_id': chat_id
            }
            
            if caption:
                data['caption'] = caption
            
            response = requests.post(url, files=files, data=data, timeout=config.PROCESSING_TIMEOUT)
            
            if response.status_code == 200:
                logger.info(f"Document {filename} sent to {chat_id}")
                return True
            else:
                logger.error(f"Failed to send document: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending document: {e}")
            return False
    
    def send_error(self, chat_id: int, error_message: str) -> bool:
        """Отправка сообщения об ошибке"""
        text = f"❌ *Ошибка при обработке:*\n\n{error_message}"
        return self.send_message(chat_id, text, parse_mode="Markdown")
    
    def send_message_with_keyboard(self, chat_id: int, text: str, 
                                   keyboard: dict, parse_mode: str = "Markdown") -> bool:
        """
        Отправка текстового сообщения с inline клавиатурой
        
        Args:
            chat_id: ID чата пользователя
            text: Текст сообщения
            keyboard: Словарь с inline_keyboard (формат Telegram API)
            parse_mode: Режим парсинга (HTML или Markdown)
        
        Returns:
            bool: True если успешно, False иначе
        """
        try:
            url = f"{self.api_url}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": keyboard
            }
            
            response = requests.post(url, json=data, timeout=config.MESSAGE_TIMEOUT)
            
            if response.status_code == 200:
                logger.info(f"Message with keyboard sent to {chat_id}")
                return True
            else:
                logger.error(f"Failed to send message with keyboard: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending message with keyboard: {e}")
            return False

