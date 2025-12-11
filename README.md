# Telegram Bot для извлечения участников чата

Бот для анализа экспорта истории Telegram-чатов и извлечения списка участников, упоминаний и каналов.

## Возможности

- Загрузка JSON-экспортов истории чатов через WebApp
- Автоматическое объединение файлов одного чата (по name, type, id)
- Извлечение участников из `from_id` в сообщениях
- Извлечение упоминаний @username из текста сообщений
- Определение каналов из пересланных сообщений
- Формирование Excel-отчетов (>= 51 участник) или текстовых списков (< 50 участников)
- Отправка результатов напрямую в Telegram
- Обработка без сохранения данных на сервере (файлы удаляются сразу после обработки)

## Требования

- Docker и Docker Compose
- Токен бота от @BotFather
- Python 3.11+ (для локальной разработки)

## Быстрый старт

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd sf3-hackaton
```

2. Создайте файл `.env`:
```bash
cp .env.example .env
# Отредактируйте .env и укажите BOT_TOKEN от @BotFather
```

3. Запустите через Docker Compose:
```bash
docker-compose up -d
```

4. Проверьте статус:
```bash
docker-compose ps
```

5. Просмотрите логи:
```bash
# Все логи
docker-compose logs -f

# Только бот
docker-compose logs -f bot

# Только веб-сервер
docker-compose logs -f web
```

## Структура проекта

```
sf3-hackaton/
├── bot/                    # Telegram бот (aiogram 3.x)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   └── src/
│       ├── bot.py          # Класс TelegramBot
│       ├── handlers.py     # Обработчики команд
│       └── utils.py        # Утилиты и конфигурация
├── web/                    # Flask веб-сервер и WebApp
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py              # Flask приложение
│   ├── config.py           # Конфигурация
│   ├── processors.py       # Парсер чатов
│   ├── excel_generator.py  # Генератор Excel
│   ├── telegram_sender.py  # Отправка в Telegram
│   └── templates/
│       └── index.html      # WebApp интерфейс
├── docker-compose.yml      # Docker Compose конфигурация
├── .env                    # Переменные окружения
├── README.md               # Этот файл
└── USER_GUIDE.md           # Руководство пользователя
```

## Ограничения

- **Формат файлов:** только JSON (экспорт из Telegram Desktop)
- **Количество файлов:** максимум 10 за раз
- **Размер файла:** до 2 ГБ каждый (лимит WebApp, не Telegram API)
- **Кодировка:** UTF-8
- **Хранение:** файлы не сохраняются на сервере, удаляются сразу после обработки

## Технические детали

### Архитектура

```
Пользователь → Telegram Bot → WebApp → Flask Server
→ Парсинг JSON → Извлечение данных → Генерация результата
→ Отправка через Telegram API → Пользователь
```

### Группировка файлов

Файлы автоматически группируются по заголовку чата:
- `name` - название чата
- `type` - тип чата (private_group, supergroup, etc.)
- `id` - ID чата

Если несколько файлов имеют одинаковый заголовок, они объединяются в один результат.

### Формат результата

- **< 50 участников:** текстовый список в чате
- **>= 51 участник:** Excel файл с тремя листами:
  - Участники
  - Упоминания
  - Каналы

### Доступные данные

Из экспорта Telegram можно извлечь:
- ✅ `from_id` - ID участника
- ✅ `from` - имя участника
- ✅ `@username` - только из упоминаний в тексте
- ❌ Username участника (недоступен в экспорте)
- ❌ Описание профиля (недоступно)
- ❌ Дата регистрации (недоступна)
- ❌ Наличие канала в профиле (недоступно)

## Документация

- **Руководство пользователя:** [USER_GUIDE.md](USER_GUIDE.md) - как экспортировать чат и использовать бота
- **API документация:** см. код в `web/app.py`

## Разработка

### Локальная разработка без Docker

```bash
# Бот
cd bot
pip install -r requirements.txt
export BOT_TOKEN=your_token
export BACKEND_URL=http://localhost:5000
python main.py

# Веб-сервер (в другом терминале)
cd web
pip install -r requirements.txt
export BOT_TOKEN=your_token
export FLASK_ENV=development
python app.py
```

### Обновление кода

```bash
# Остановить контейнеры
docker-compose down

# Пересобрать и запустить
docker-compose up -d --build
```

### Просмотр логов

```bash
# Все логи
docker-compose logs -f

# Последние 100 строк
docker-compose logs --tail=100

# Конкретный сервис
docker-compose logs -f bot
docker-compose logs -f web
```

## Лицензия

Проект создан для хакатона SF3 Hackaton.

