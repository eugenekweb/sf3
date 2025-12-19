from datetime import datetime
import html
from io import BytesIO
from typing import List, Dict
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
import logging

logger = logging.getLogger(__name__)


class ExcelGenerator:
    """Генератор Excel файлов для результатов анализа чата"""

    def __init__(self):
        self.wb = None
        self.export_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def create_workbook(self):
        """Создание новой рабочей книги"""
        self.wb = openpyxl.Workbook()
        # Удаляем дефолтный лист
        if "Sheet" in self.wb.sheetnames:
            self.wb.remove(self.wb["Sheet"])

    def create_sheet(
        self, name: str, headers: List[str]
    ) -> openpyxl.worksheet.worksheet.Worksheet:
        """Создание листа"""
        ws = self.wb.create_sheet(title=name)

        # Автоширина колонок
        for col_idx in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 30

        return ws

    def add_participants_sheet(
        self, participants: List[Dict], chat_name: str = "Unknown"
    ):
        """Добавление листа с участниками"""
        headers = ["Имя-фамилия", "ИД"]

        ws = self.create_sheet("Участники", headers)

        # Заголовки на первых строках
        ws.cell(row=1, column=1, value=f"Файл истории чата: {chat_name}")
        ws.cell(row=2, column=1, value=f"Дата экспорта: {self.export_date}")
        ws.cell(row=3, column=1, value="На этой вкладке: Участники")

        # Заголовки колонок на строке 4
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col_idx, value=header)
            header_fill = PatternFill(
                start_color="4472C4", end_color="4472C4", fill_type="solid"
            )
            header_font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Данные участников (начиная со строки 5)
        for row_idx, participant in enumerate(participants, 5):
            name = participant.get("name", "Unknown")
            from_id = participant.get("from_id", "N/A")

            ws.cell(row=row_idx, column=1, value=name)
            ws.cell(row=row_idx, column=2, value=from_id)

        logger.info(f"Added {len(participants)} participants to Excel")

    def add_mentions_sheet(self, mentions: List[Dict], chat_name: str = "Unknown"):
        """Добавление листа с упоминаниями"""
        headers = ["Username"]

        ws = self.create_sheet("Упоминания", headers)

        # Заголовки на первых строках
        ws.cell(row=1, column=1, value=f"Файл истории чата: {chat_name}")
        ws.cell(row=2, column=1, value=f"Дата экспорта: {self.export_date}")
        ws.cell(row=3, column=1, value="На этой вкладке: Упоминания")

        # Заголовки колонок на строке 4
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col_idx, value=header)
            header_fill = PatternFill(
                start_color="4472C4", end_color="4472C4", fill_type="solid"
            )
            header_font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Данные упоминаний (начиная со строки 5)
        row_idx = 5
        for mention in mentions:
            username = mention.get("username", "")
            if username:
                ws.cell(row=row_idx, column=1, value=f"@{username}")
                row_idx += 1

        logger.info(f"Added {row_idx - 5} mentions to Excel")

    def add_channels_sheet(self, channels: List[Dict], chat_name: str = "Unknown"):
        """Добавление листа с каналами"""
        headers = ["Название", "ИД"]

        ws = self.create_sheet("Каналы", headers)

        # Заголовки на первых строках
        ws.cell(row=1, column=1, value=f"Файл истории чата: {chat_name}")
        ws.cell(row=2, column=1, value=f"Дата экспорта: {self.export_date}")
        ws.cell(row=3, column=1, value="На этой вкладке: Каналы")

        # Заголовки колонок на строке 4
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=4, column=col_idx, value=header)
            header_fill = PatternFill(
                start_color="4472C4", end_color="4472C4", fill_type="solid"
            )
            header_font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Данные каналов (начиная со строки 5)
        for row_idx, channel in enumerate(channels, 5):
            name = channel.get("name", "Unknown")
            channel_id = channel.get("channel_id", "N/A")

            ws.cell(row=row_idx, column=1, value=name)
            ws.cell(row=row_idx, column=2, value=channel_id)

        logger.info(f"Added {len(channels)} channels to Excel")

    def generate(
        self,
        participants: List[Dict],
        mentions: List[Dict],
        channels: List[Dict],
        chat_name: str = "Unknown",
    ) -> BytesIO:
        """
        Генерация Excel файла в памяти

        Returns:
            BytesIO: Поток с Excel файлом
        """
        self.create_workbook()

        # Добавляем вкладки: Участники, Упоминания и Каналы
        if participants:
            self.add_participants_sheet(participants, chat_name)

        # Передаем список упоминаний как есть, метод add_mentions_sheet сам его отфильтрует
        if mentions:
            self.add_mentions_sheet(mentions, chat_name)

        # Добавляем каналы, если они есть
        if channels:
            self.add_channels_sheet(channels, chat_name)

        # Сохраняем в память
        output = BytesIO()
        self.wb.save(output)
        output.seek(0)

        return output

    def generate_text_list(
        self,
        participants: List[Dict],
        mentions: List[Dict],
        channels: List[Dict],
        chat_name: str = "Unknown",
    ) -> str:
        """
        Генерация текстового списка для отправки в чат (>= 50 участников - Excel, < 50 - текст)
        Формат: имя (ИД) в code блоке для копирования (HTML форматирование)

        Returns:
            str: Текстовое представление списка в формате HTML
        """
        # Экранируем chat_name сразу в начале функции для использования везде
        chat_name_escaped = html.escape(chat_name)
        
        # Используем HTML для надежного форматирования в Telegram
        text = f"📊 <b>Результаты анализа чата: {chat_name_escaped}</b>\n\n"

        if participants:
            text += f"👤 <b>Участники ({len(participants)}):</b>\n"
            # Формируем список без нумерации
            participants_list = []
            for p in participants:
                name = p.get("name", "Unknown")
                from_id = p.get("from_id", "N/A")
                # Экранируем HTML спецсимволы
                name_escaped = html.escape(name)
                from_id_escaped = html.escape(str(from_id))
                participants_list.append(f"{name_escaped} ({from_id_escaped})")
            # Оборачиваем в HTML pre/code блок для моноширинного шрифта
            text += "<pre><code>" + "\n".join(participants_list) + "</code></pre>\n\n"

        # Показываем только упоминания с username
        mentions_with_username = [m for m in mentions if m.get("username")]
        if mentions_with_username:
            text += f"👥 <b>Упоминания ({len(mentions_with_username)}):</b>\n"
            # Формируем список без нумерации
            mentions_list = []
            for m in mentions_with_username:
                username = m.get("username", "")
                # Экранируем HTML спецсимволы
                username_escaped = html.escape(username)
                mentions_list.append(f"@{username_escaped}")
            # Оборачиваем в HTML pre/code блок
            text += "<pre><code>" + "\n".join(mentions_list) + "</code></pre>\n\n"

        # Показываем каналы, если они есть
        if channels:
            text += f"📢 <b>Каналы ({len(channels)}):</b>\n"
            # Формируем список без нумерации
            channels_list = []
            for ch in channels:
                name = ch.get("name", "Unknown")
                channel_id = ch.get("channel_id", "N/A")
                # Экранируем HTML спецсимволы
                name_escaped = html.escape(name)
                channel_id_escaped = html.escape(str(channel_id))
                channels_list.append(f"{name_escaped} ({channel_id_escaped})")
            # Оборачиваем в HTML pre/code блок
            text += "<pre><code>" + "\n".join(channels_list) + "</code></pre>\n\n"

        # Добавляем информацию об обработке в конец
        # chat_name_escaped уже определен выше
        text += "✅ <b>Обработка завершена!</b>\n\n"
        text += f"💬 <b>Чат:</b> {chat_name_escaped}\n"
        text += f"👤 Участников: {len(participants)}\n"
        text += f"👥 Упоминаний: {len(mentions_with_username)}"
        if channels:
            text += f"\n📢 Каналов: {len(channels)}"

        return text
