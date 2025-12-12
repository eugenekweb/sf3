#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ENV_FILE=".env"
PORT=5000
TUNA_IMAGE="yuccastream/tuna:latest"
CONTAINER_NAME="tuna_tunnel"

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Настройка Tuna Tunnel                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Проверяем наличие docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker не установлен${NC}"
    exit 1
fi

# Проверяем наличие .env файла
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}⚠️  Файл .env не найден, создаю из примера...${NC}"
    if [ -f ".env.example" ]; then
        cp .env.example "$ENV_FILE"
        echo -e "${GREEN}✅ Создан файл .env из .env.example${NC}"
        echo -e "${YELLOW}⚠️  Не забудьте заполнить BOT_TOKEN и TUNA_TOKEN в .env!${NC}"
    else
        echo -e "${RED}❌ Файл .env.example не найден${NC}"
        exit 1
    fi
fi

# Читаем токен из .env или аргумента
TUNA_TOKEN="${1:-}"
if [ -z "$TUNA_TOKEN" ]; then
    # Пытаемся прочитать из .env
    if grep -q "^TUNA_TOKEN=" "$ENV_FILE"; then
        TUNA_TOKEN=$(grep "^TUNA_TOKEN=" "$ENV_FILE" | cut -d '=' -f2 | tr -d '"' | tr -d "'" | xargs)
    fi
fi

if [ -z "$TUNA_TOKEN" ] || [ "$TUNA_TOKEN" = "your_tuna_token_here" ] || [ "$TUNA_TOKEN" = "<токен_туннеля>" ]; then
    echo -e "${RED}❌ TUNA_TOKEN не указан${NC}"
    echo -e "${YELLOW}Укажите токен одним из способов:${NC}"
    echo -e "  1. Как аргумент: ${GREEN}$0 <token>${NC}"
    echo -e "  2. В файле .env: ${GREEN}TUNA_TOKEN=your_token${NC}"
    exit 1
fi

# Обновляем токен в .env
echo -e "${YELLOW}📝 Обновляю TUNA_TOKEN в $ENV_FILE${NC}"
if grep -q "^TUNA_TOKEN=" "$ENV_FILE"; then
    # Обновляем существующий токен
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s|^TUNA_TOKEN=.*|TUNA_TOKEN=$TUNA_TOKEN|" "$ENV_FILE"
    else
        # Linux/Git Bash
        sed -i "s|^TUNA_TOKEN=.*|TUNA_TOKEN=$TUNA_TOKEN|" "$ENV_FILE"
    fi
else
    # Добавляем новый токен
    echo "TUNA_TOKEN=$TUNA_TOKEN" >> "$ENV_FILE"
fi

# Проверяем наличие BOT_TOKEN
if ! grep -q "^BOT_TOKEN=" "$ENV_FILE" || grep -q "^BOT_TOKEN=$" "$ENV_FILE" || grep -q "^BOT_TOKEN=your_bot_token" "$ENV_FILE"; then
    echo -e "${RED}❌ BOT_TOKEN не настроен в .env${NC}"
    echo -e "${YELLOW}Откройте .env и укажите BOT_TOKEN${NC}"
    exit 1
fi

echo -e "${YELLOW}📋 Tuna Tunnel:${NC}"
echo -e "  ✅ Бесплатный"
echo -e "  ✅ Простой в использовании"
echo -e "  ✅ Работает через Docker"
echo ""

# Проверяем, есть ли сервис tuna в docker-compose.yml (не закомментирован)
USE_DOCKER_COMPOSE=false
if [ -f "docker-compose.yml" ]; then
    # Проверяем, есть ли незакомментированный сервис tuna
    if grep -q "^[[:space:]]*tuna:" docker-compose.yml && ! grep -q "^[[:space:]]*#[[:space:]]*tuna:" docker-compose.yml; then
        USE_DOCKER_COMPOSE=true
        echo -e "${GREEN}✅ Обнаружен сервис tuna в docker-compose.yml${NC}"
    fi
fi

# Запускаем web сервер, если его нет
echo -e "${YELLOW}🐳 Проверяю web сервер...${NC}"
if ! docker ps | grep -q "web_server"; then
    echo -e "${YELLOW}🚀 Запускаю web сервер...${NC}"
    docker-compose up -d web
    echo -e "${YELLOW}⏳ Жду запуска web сервера (5 секунд)...${NC}"
    sleep 5
else
    echo -e "${GREEN}✅ Web сервер уже запущен${NC}"
fi

if [ "$USE_DOCKER_COMPOSE" = true ]; then
    # Используем docker-compose для запуска tuna
    echo -e "${YELLOW}🚀 Запускаю туннель Tuna через docker-compose...${NC}"
    
    # Останавливаем старый контейнер, если он был запущен через docker run
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
    
    # Сохраняем токен в volume перед запуском (если volume еще не создан)
    echo -e "${YELLOW}🔐 Сохраняю токен в конфигурацию Tuna...${NC}"
    
    # Создаем volume для конфигурации, если его нет
    docker volume create tuna_config > /dev/null 2>&1 || true
    
    # Сохраняем токен через временный контейнер с volume
    docker run --rm \
        -v tuna_config:/root/.config/tuna \
        "$TUNA_IMAGE" config save-token "$TUNA_TOKEN" 2>&1 || {
        echo -e "${YELLOW}⚠️  Не удалось сохранить токен через Docker команду, пробую альтернативный способ...${NC}"
        # Альтернативный способ: создаем временный контейнер и записываем токен напрямую
        docker run --rm \
            -v tuna_config:/root/.config/tuna \
            --entrypoint sh \
            "$TUNA_IMAGE" \
            -c "mkdir -p /root/.config/tuna && echo '$TUNA_TOKEN' > /root/.config/tuna/token" 2>&1 || {
            echo -e "${YELLOW}⚠️  Альтернативный способ тоже не сработал, но продолжаем...${NC}"
        }
    }
    
    # Запускаем через docker-compose
    docker-compose up -d tuna || {
        echo -e "${RED}❌ Не удалось запустить туннель через docker-compose${NC}"
        exit 1
    }
    
    # Используем имя контейнера из docker-compose
    CONTAINER_NAME="tuna_tunnel"
else
    # Используем старую логику с docker run
    echo -e "${YELLOW}📋 Используется режим docker run (сервис tuna не найден в docker-compose.yml)${NC}"
    
    # Останавливаем старые контейнеры
    echo -e "${YELLOW}🛑 Останавливаю старые контейнеры...${NC}"
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
    
    # Скачиваем образ Tuna
    echo -e "${YELLOW}📦 Скачиваю образ Tuna...${NC}"
    docker pull "$TUNA_IMAGE" || {
        echo -e "${RED}❌ Не удалось скачать образ $TUNA_IMAGE${NC}"
        exit 1
    }
    
    # Сохраняем токен через Docker контейнер
    echo -e "${YELLOW}🔐 Сохраняю токен в конфигурацию Tuna...${NC}"
    
    # Создаем volume для конфигурации, если его нет
    docker volume create tuna_config > /dev/null 2>&1 || true
    
    # Сохраняем токен через временный контейнер с volume
    docker run --rm \
        -v tuna_config:/root/.config/tuna \
        "$TUNA_IMAGE" config save-token "$TUNA_TOKEN" 2>&1 || {
        echo -e "${YELLOW}⚠️  Не удалось сохранить токен через Docker команду, пробую альтернативный способ...${NC}"
        # Альтернативный способ: создаем временный контейнер и записываем токен напрямую
        docker run --rm \
            -v tuna_config:/root/.config/tuna \
            --entrypoint sh \
            "$TUNA_IMAGE" \
            -c "mkdir -p /root/.config/tuna && echo '$TUNA_TOKEN' > /root/.config/tuna/token" 2>&1 || {
            echo -e "${YELLOW}⚠️  Альтернативный способ тоже не сработал, но продолжаем...${NC}"
        }
    }
    
    # Определяем имя сети Docker Compose
    NETWORK_NAME=$(docker network ls | grep -E "app_network|sf3-hackaton|hackaton" | head -1 | awk '{print $2}' || echo "app_network")
    
    # Создаем сеть, если её нет
    if ! docker network inspect "$NETWORK_NAME" > /dev/null 2>&1; then
        echo -e "${YELLOW}📡 Создаю сеть $NETWORK_NAME...${NC}"
        docker network create "$NETWORK_NAME" > /dev/null 2>&1 || {
            echo -e "${YELLOW}⚠️  Не удалось создать сеть, использую host режим...${NC}"
            NETWORK_NAME="host"
        }
    fi
    
    # Запускаем туннель в Docker контейнере
    echo -e "${YELLOW}🚀 Запускаю туннель Tuna в Docker...${NC}"
    if [ "$NETWORK_NAME" = "host" ]; then
        # Используем host режим и localhost
        docker run -d \
            --name "$CONTAINER_NAME" \
            --network host \
            -v tuna_config:/root/.config/tuna \
            "$TUNA_IMAGE" http localhost:5000 > /dev/null 2>&1 || {
            echo -e "${RED}❌ Не удалось запустить туннель${NC}"
            exit 1
        }
    else
        # Используем Docker сеть и имя сервиса web
        docker run -d \
            --name "$CONTAINER_NAME" \
            --network "$NETWORK_NAME" \
            -v tuna_config:/root/.config/tuna \
            "$TUNA_IMAGE" http web:5000 > /dev/null 2>&1 || {
            echo -e "${RED}❌ Не удалось запустить туннель${NC}"
            exit 1
        }
    fi
fi

# Ждем, пока туннель запустится и выведет URL
echo -e "${YELLOW}⏳ Ожидаю инициализации туннеля (10 секунд)...${NC}"
sleep 10

# Ищем URL в логах (разные варианты формата)
TUNNEL_URL=""
for i in {1..20}; do
    LOG_OUTPUT=$(docker logs "$CONTAINER_NAME" 2>&1)
    
    # Пробуем разные паттерны поиска URL
    TUNNEL_URL=$(echo "$LOG_OUTPUT" | grep -oP 'https://[a-zA-Z0-9\-]+\.ru\.tuna\.am' | head -1 || echo "")
    
    # Если не нашли с https://, пробуем без него
    if [ -z "$TUNNEL_URL" ]; then
        TUNNEL_URL=$(echo "$LOG_OUTPUT" | grep -oP '[a-zA-Z0-9\-]+\.ru\.tuna\.am' | head -1 || echo "")
        if [ -n "$TUNNEL_URL" ]; then
            TUNNEL_URL="https://$TUNNEL_URL"
        fi
    fi
    
    # Еще один вариант - ищем любую строку с ru.tuna.am
    if [ -z "$TUNNEL_URL" ]; then
        TUNNEL_URL=$(echo "$LOG_OUTPUT" | grep -i 'ru\.tuna\.am' | grep -oP 'https?://[^\s]+' | head -1 || echo "")
    fi
    
    if [ -n "$TUNNEL_URL" ]; then
        # Убеждаемся что URL начинается с https://
        if [[ ! "$TUNNEL_URL" =~ ^https:// ]]; then
            TUNNEL_URL="https://$TUNNEL_URL"
        fi
        break
    fi
    
    echo -e "${YELLOW}⏳ Попытка $i/20, ожидаю инициализации туннеля...${NC}"
    sleep 2
done

# Если не получили автоматически - просим пользователя
if [ -z "$TUNNEL_URL" ]; then
    echo -e "${YELLOW}Туннель запущен, но URL не получен автоматически.${NC}"
    echo -e "${YELLOW}Логи контейнера:${NC}"
    docker logs "$CONTAINER_NAME" 2>&1 | tail -30
    echo ""
    echo -e "${YELLOW}Введите полный URL туннеля (пример: https://ntl6xh-109-107-165-72.ru.tuna.am):${NC}"
    read -r TUNNEL_URL
fi

# Убеждаемся что URL начинается с https://
if [ -n "$TUNNEL_URL" ] && [[ ! "$TUNNEL_URL" =~ ^https:// ]]; then
    TUNNEL_URL="https://$TUNNEL_URL"
fi

if [ -z "$TUNNEL_URL" ]; then
    echo -e "${RED}❌ Не удалось получить URL${NC}"
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
    exit 1
fi

# Обновляем .env
echo -e "${YELLOW}📝 Обновляю BACKEND_URL в $ENV_FILE${NC}"

if [ -f "$ENV_FILE" ]; then
    if grep -q "^BACKEND_URL=" "$ENV_FILE"; then
        ESCAPED_URL=$(echo "$TUNNEL_URL" | sed 's/\//\\\//g')
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            sed -i '' "s|^BACKEND_URL=.*|BACKEND_URL=$ESCAPED_URL|" "$ENV_FILE"
        else
            # Linux/Git Bash
            sed -i "s|^BACKEND_URL=.*|BACKEND_URL=$ESCAPED_URL|" "$ENV_FILE"
        fi
    else
        echo "BACKEND_URL=$TUNNEL_URL" >> "$ENV_FILE"
    fi
else
    echo "BACKEND_URL=$TUNNEL_URL" > "$ENV_FILE"
fi

# Проверяем, что URL обновился
if grep -q "^BACKEND_URL=$TUNNEL_URL" "$ENV_FILE" || grep -q "^BACKEND_URL=$ESCAPED_URL" "$ENV_FILE"; then
    echo -e "${GREEN}✅ BACKEND_URL обновлён в $ENV_FILE${NC}"
else
    echo -e "${YELLOW}⚠️  Проверьте, что BACKEND_URL обновился в $ENV_FILE${NC}"
fi

echo -e "${GREEN}✅ .env обновлён${NC}"
echo -e "🔗 URL: ${GREEN}$TUNNEL_URL${NC}"
echo -e "📄 Файл: ${GREEN}$ENV_FILE${NC}"
echo -e "🐳 Контейнер: ${GREEN}$CONTAINER_NAME${NC}"

# Запуск Docker Compose для бота
echo ""
echo -e "${YELLOW}🐳 Запускаю Docker Compose (бот)...${NC}"

if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}❌ Ошибка: docker-compose.yml не найден${NC}"
    if [ "$USE_DOCKER_COMPOSE" = false ]; then
        docker stop "$CONTAINER_NAME" 2>/dev/null || true
        docker rm "$CONTAINER_NAME" 2>/dev/null || true
    fi
    exit 1
fi

docker-compose up -d bot

echo ""
echo -e "${GREEN}=== ВСЁ ГОТОВО ===${NC}"
echo -e "🔗 Туннель: ${GREEN}$TUNNEL_URL${NC}"
echo -e "🐳 Docker: ${GREEN}запущен${NC}"
echo ""
echo -e "${YELLOW}Проверка статуса контейнеров:${NC}"
docker-compose ps
docker ps | grep "$CONTAINER_NAME" || echo -e "${YELLOW}⚠️  Контейнер $CONTAINER_NAME не найден в списке${NC}"

echo ""
echo -e "${YELLOW}Логи туннеля (Ctrl+C для выхода):${NC}"
echo -e "${BLUE}Для просмотра логов используйте:${NC}"
echo -e "  ${GREEN}docker logs -f $CONTAINER_NAME${NC}"
