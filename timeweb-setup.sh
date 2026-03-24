#!/bin/bash
set -e

echo "=== 1С Хелпер — Установка на Timeweb VPS ==="
echo ""

# ── 1. Docker ────────────────────────────────────────────────────────
if ! command -v docker &> /dev/null; then
    echo "[1/6] Устанавливаю Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
else
    echo "[1/6] Docker уже установлен"
fi

if ! docker compose version &> /dev/null 2>&1; then
    apt-get install -y docker-compose-plugin
fi

# ── 2. Node.js (для сборки miniapp) ─────────────────────────────────
if ! command -v node &> /dev/null; then
    echo "[2/6] Устанавливаю Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
else
    echo "[2/6] Node.js уже установлен: $(node -v)"
fi

# ── 3. Получаю IP и формирую домен ──────────────────────────────────
SERVER_IP=$(curl -s https://api.ipify.org)
DOMAIN="${SERVER_IP//./-}.nip.io"
echo "[3/6] IP: $SERVER_IP → домен: https://$DOMAIN"

# ── 4. Клонируем / обновляем репозиторий ────────────────────────────
if [ ! -d "/app/.git" ]; then
    echo "[4/6] Клонирую репозиторий..."
    git clone https://github.com/Crystalysdes/onec-helper /app
else
    echo "[4/6] Обновляю репозиторий..."
    git -C /app pull
fi

# ── 5. .env файл ─────────────────────────────────────────────────────
cd /app

if [ ! -f ".env" ]; then
    echo "[5/6] Создаю .env..."
    cat > .env << ENVEOF
DATABASE_URL=postgresql+asyncpg://neondb_owner:npg_mJMfgdQi9c1C@ep-spring-paper-am95fxjb-pooler.c-5.us-east-1.aws.neon.tech/neondb
BACKEND_DOMAIN=${DOMAIN}
BACKEND_URL=https://${DOMAIN}
MINIAPP_URL=https://${DOMAIN}
ENVIRONMENT=production
BOT_TOKEN=ЗАМЕНИ_МЕНЯ
SECRET_KEY=ЗАМЕНИ_МЕНЯ
ANTHROPIC_API_KEY=ЗАМЕНИ_МЕНЯ
ENCRYPTION_KEY=ЗАМЕНИ_МЕНЯ
ENVEOF

    echo ""
    echo "┌─────────────────────────────────────────────────────────┐"
    echo "│  ВАЖНО: заполни секретные переменные в /app/.env        │"
    echo "│  nano /app/.env  (Ctrl+X, Y для сохранения)             │"
    echo "└─────────────────────────────────────────────────────────┘"
    echo ""
    read -p "Нажми Enter когда заполнишь .env..."
else
    sed -i "s|BACKEND_DOMAIN=.*|BACKEND_DOMAIN=${DOMAIN}|" .env
    sed -i "s|BACKEND_URL=.*|BACKEND_URL=https://${DOMAIN}|" .env
    sed -i "s|MINIAPP_URL=.*|MINIAPP_URL=https://${DOMAIN}|" .env
    echo "[5/6] .env обновлён (домен: $DOMAIN)"
fi

# ── 6. Собираем miniapp с правильным API URL ─────────────────────────
echo "[6/6] Собираю miniapp..."
cd /app/miniapp
npm install --silent
VITE_API_URL="https://${DOMAIN}/api/v1" npm run build
echo "      miniapp собран → /app/miniapp/dist"

# ── 7. Запускаем ────────────────────────────────────────────────────
cd /app
echo ""
echo "=== Запускаю контейнеры ==="
docker compose -f docker-compose.timeweb.yml up -d --build

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║  ГОТОВО!                                                  ║"
echo "╠═══════════════════════════════════════════════════════════╣"
echo "║  Сайт + API:  https://$DOMAIN"
echo "║  Бот:         @oneshelperbot                              ║"
echo "║                                                           ║"
echo "║  Логи:  docker compose -f /app/docker-compose.timeweb.yml logs -f  ║"
echo "║  Обновить:  cd /app && git pull && bash timeweb-setup.sh  ║"
echo "╚═══════════════════════════════════════════════════════════╝"
