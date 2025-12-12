from datetime import datetime
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

        # Добавляем только 2 вкладки: Участники и Упоминания
        if participants:
            self.add_participants_sheet(participants, chat_name)

        # Фильтруем упоминания с username и передаем отфильтрованный список
        mentions_with_username = [m for m in mentions if m.get("username")]
        if mentions_with_username:
            self.add_mentions_sheet(mentions_with_username, chat_name)

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
        Генерация текстового списка для отправки в чат (< EXCEL_THRESHOLD участников)
        Формат: имя (ИД) в code блоке для копирования (markdown с тройными кавычками)

        Returns:
            str: Текстовое представление списка
        """
        text = f"📊 *Результаты анализа чата: {chat_name}*\n\n"

        if participants:
            text += f"👤 *Участники ({len(participants)}):*\n"
            # Формируем список без нумерации
            participants_list = []
            for p in participants:
                name = p.get("name", "Unknown")
                from_id = p.get("from_id", "N/A")
                participants_list.append(f"{name} ({from_id})")
            # Оборачиваем в markdown code блок с тройными кавычками
            text += "```\n" + "\n".join(participants_list) + "\n```\n\n"

        # Показываем только упоминания с username
        mentions_with_username = [m for m in mentions if m.get("username")]
        if mentions_with_username:
            text += f"👥 *Упоминания ({len(mentions_with_username)}):*\n"
            # Формируем список без нумерации
            mentions_list = []
            for m in mentions_with_username:
                username = m.get("username", "")
                mentions_list.append(f"@{username}")
            # Оборачиваем в markdown code блок с тройными кавычками
            text += "```\n" + "\n".join(mentions_list) + "\n```\n\n"

        # Добавляем информацию об обработке в конец
        text += "✅ *Обработка завершена!*\n\n"
        text += f"💬 *Чат:* {chat_name}\n"
        text += f"👤 Участников: {len(participants)}\n"
        text += f"👥 Упоминаний: {len(mentions_with_username)}"

        return text
