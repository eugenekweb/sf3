import json
import logging
import chardet
from typing import Dict, List, Set, Tuple
from collections import defaultdict
from config import config

logger = logging.getLogger(__name__)


class ChatParser:
    """Парсер экспорта Telegram чата"""

    def __init__(self):
        self.participants: Dict[str, Dict] = {}
        self.mentions: Dict[str, Dict] = {}
        self.channels: Dict[str, Dict] = {}
        self.deleted_accounts: Set[str] = set()

    def parse_file(self, filepath: str) -> Dict:
        """Парсинг одного JSON файла с проверкой кодировки и структуры"""
        try:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                with open(filepath, "rb") as f:
                    raw_data = f.read()
                    detected = chardet.detect(raw_data)
                    
                    if detected:
                        encoding = (detected.get("encoding") or "").lower()
                        confidence = detected.get("confidence", 0)
                        # Разрешаем UTF-8, UTF-8-SIG и ASCII (как подмножество UTF-8)
                        if encoding in ["utf-8", "utf-8-sig", "ascii"]:
                            pass  # Валидные кодировки, продолжаем обработку
                        elif confidence > config.ENCODING_CONFIDENCE_THRESHOLD:
                            raise ValueError(
                                f"Файл не в кодировке UTF-8. Обнаружена кодировка: {detected['encoding']} "
                                f"(уверенность: {confidence:.0%}). Конвертируйте файл в UTF-8."
                            )
                    try:
                        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                            data = json.load(f)
                    except json.JSONDecodeError:
                        raise ValueError(f"Ошибка парсинга JSON. Возможно, файл поврежден или не является JSON.")
                    except Exception:
                        raise e

            if "messages" not in data:
                raise ValueError(
                    "Файл не содержит поле 'messages'. Это не экспорт Telegram чата?"
                )
            
            if not isinstance(data.get("messages"), list):
                raise ValueError(
                    "Поле 'messages' должно быть массивом. Это не экспорт Telegram чата?"
                )

            return {
                "name": data.get("name", "Неизвестный чат"),
                "type": data.get("type", "unknown"),
                "id": data.get("id"),
                "messages": data.get("messages", []),
            }
        except UnicodeDecodeError as e:
            raise ValueError(f"Ошибка декодирования UTF-8: {e}. Файл должен быть в кодировке UTF-8.")
        except json.JSONDecodeError as e:
            raise ValueError(f"Ошибка парсинга JSON: {e}")
        except ValueError as e:
            # Пробрасываем ValueError как есть (наши проверки)
            raise
        except Exception as e:
            raise ValueError(f"Ошибка чтения файла: {e}")

    def extract_participants(self, messages: List[Dict]) -> None:
        """Извлечение участников из сообщений"""
        for msg in messages:
            if msg.get("type") == "message":
                from_id = msg.get("from_id")
                from_name = msg.get("from")

                if not from_id or from_id in self.deleted_accounts:
                    continue

                if isinstance(from_id, str) and "deleted" in from_id.lower():
                    self.deleted_accounts.add(from_id)
                    continue

                if from_id not in self.participants:
                    self.participants[from_id] = {
                        "from_id": from_id,
                        "name": from_name or "Unknown",
                    }

            forwarded_from_id = msg.get("forwarded_from_id")
            forwarded_from_name = msg.get("forwarded_from")

            if forwarded_from_id and forwarded_from_name:
                if (
                    isinstance(forwarded_from_id, str)
                    and "channel" in forwarded_from_id.lower()
                ):
                    continue

                if forwarded_from_id not in self.participants:
                    self.participants[forwarded_from_id] = {
                        "from_id": forwarded_from_id,
                        "name": forwarded_from_name,
                    }

    def extract_mentions(self, messages: List[Dict]) -> None:
        """
        Извлечение упоминаний @username и mention_name из текста сообщений
        Кейс 2: mention_name + user_id (только если такого ИД нет в participants)
        """
        for msg in messages:
            text = msg.get("text", "")

            # Парсим только если text - это список объектов
            if not isinstance(text, list):
                continue

            for item in text:
                if not isinstance(item, dict):
                    continue

                item_type = item.get("type")

                # Обработка mention (@username)
                if item_type == "mention":
                    username_text = item.get("text", "")
                    # Убираем @ из начала
                    if username_text.startswith("@"):
                        username = username_text[1:]
                    else:
                        username = username_text

                    if username and username not in self.mentions:
                        self.mentions[username] = {"username": username}

                # Кейс 2: Обработка mention_name (упоминание по имени из контактов)
                # Только если такого user_id еще нет в participants
                elif item_type == "mention_name":
                    mention_name = item.get("text", "")
                    user_id = item.get("user_id")

                    if user_id and mention_name:
                        user_id_str = f"user{user_id}"

                        # Добавляем только если такого ИД еще нет в participants
                        if user_id_str not in self.participants:
                            # Сохраняем как участника (строгая пара: имя - ИД)
                            self.participants[user_id_str] = {
                                "from_id": user_id_str,
                                "name": mention_name,
                            }

    def extract_channels(self, messages: List[Dict]) -> None:
        """
        Извлечение каналов из сообщений
        Кейс 4: from + from_id (содержит "channel") + непустой text
        """
        for msg in messages:
            from_id = msg.get("from_id")
            from_name = msg.get("from")
            text = msg.get("text", "")

            # Кейс 4: Проверяем, что это канал
            # Должно быть: имя канала, ИД содержит "channel", и есть непустой текст
            if (
                from_id
                and from_name
                and isinstance(from_id, str)
                and "channel" in from_id.lower()
            ):
                # Проверяем, что text не пустой (может быть строка или список)
                # Текст может быть в любом месте структуры сообщения
                text_is_empty = True
                if isinstance(text, str):
                    text_is_empty = not text.strip()
                elif isinstance(text, list):
                    # Если список, проверяем, есть ли хотя бы один непустой элемент
                    text_is_empty = not any(
                        item
                        for item in text
                        if (isinstance(item, str) and item.strip())
                        or (isinstance(item, dict) and item.get("text", "").strip())
                    )
                elif not text:
                    # Если text отсутствует или None
                    text_is_empty = True

                if not text_is_empty:
                    # Сохраняем канал (строгая пара: имя - ИД)
                    if from_id not in self.channels:
                        self.channels[from_id] = {
                            "channel_id": from_id,
                            "name": from_name,
                        }


    def process_messages(self, messages: List[Dict]) -> None:
        """Обработка всех сообщений для извлечения данных"""
        self.extract_participants(messages)
        self.extract_mentions(messages)
        self.extract_channels(messages)

    def get_results(self) -> Dict:
        """Получение результатов парсинга"""
        return {
            "participants": list(self.participants.values()),
            "mentions": list(self.mentions.values()),
            "channels": list(self.channels.values()),
            "total_participants": len(self.participants),
            "total_mentions": len(self.mentions),
            "total_channels": len(self.channels),
        }

    def reset(self):
        """Сброс состояния парсера"""
        self.participants.clear()
        self.mentions.clear()
        self.channels.clear()
        self.deleted_accounts.clear()


class FileGrouper:
    """Группировка файлов по чатам"""

    @staticmethod
    def group_files(file_data_list: List[Dict]) -> Dict[Tuple, List[Dict]]:
        """
        Группировка файлов по заголовку чата.
        Приоритет: id (если есть), иначе (name, type).
        Это позволяет группировать файлы одного чата, даже если name отличается или отсутствует.

        Args:
            file_data_list: Список словарей с данными файлов {'name', 'type', 'id', 'messages', 'filepath'}

        Returns:
            Словарь: (name, type, id) -> список файлов этого чата
        """
        groups = defaultdict(list)

        for file_data in file_data_list:
            chat_id = file_data.get("id")
            chat_type = file_data.get("type")
            chat_name = file_data.get("name")
            
            if chat_id:
                key = (None, chat_type, chat_id)
            else:
                key = (chat_name, chat_type, None)
            
            groups[key].append(file_data)

        result = {}
        for key, files in groups.items():
            final_name = None
            for file_data in files:
                name = file_data.get("name")
                if name and name != "Неизвестный чат":
                    final_name = name
                    break
            
            if not final_name and files:
                final_name = files[0].get("name") or "Неизвестный чат"
            
            final_key = (final_name, key[1], key[2])
            result[final_key] = files

        return result

    @staticmethod
    def merge_messages(file_data_list: List[Dict]) -> List[Dict]:
        """Объединение сообщений из нескольких файлов одного чата"""
        all_messages = []
        for file_data in file_data_list:
            all_messages.extend(file_data.get("messages", []))
        return all_messages
