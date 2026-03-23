# 1С Хелпер — AI-ассистент для управления товарами

Telegram Mini App платформа для владельцев розничных магазинов.  
Позволяет управлять товарами через Telegram с интеграцией 1С и AI-обработкой.

## Возможности

- 📦 Управление товарами (добавление, редактирование, удаление)
- 📷 Сканирование штрих-кодов через камеру
- 🤖 AI-распознавание товаров по фото (Claude)
- 📄 Загрузка и обработка накладных (OCR + Claude AI)
- 🔄 Интеграция с 1С через OData REST API
- 📊 Отчёты: остатки, стоимость склада, малый остаток
- 👑 Панель администратора
- 🔐 Мультитенантная архитектура (каждый пользователь — отдельный аккаунт)

---

## Технологический стек

| Компонент | Технология |
|-----------|-----------|
| Backend | Python 3.11 + FastAPI |
| Telegram Bot | aiogram 3 |
| Frontend | React 18 + Vite + TailwindCSS |
| База данных | PostgreSQL 15 |
| Кэш | Redis 7 |
| AI | Claude API (Anthropic) |
| OCR | Tesseract + OpenCV |
| Штрих-коды | pyzbar + OpenCV |
| Прокси | Nginx |

---

## Быстрый старт

### 1. Клонирование

```bash
git clone <repo-url>
cd "1с хелпер"
```

### 2. Настройка переменных окружения

```bash
cp .env.example .env
```

Отредактируйте `.env`:

```env
BOT_TOKEN=8241924602:AAHxqUWIR3II3JHliS22TM6kCw-PhKONh8A
ADMIN_TELEGRAM_ID=5504548686
ANTHROPIC_API_KEY=sk-ant-ваш-ключ
MINIAPP_URL=https://ваш-домен.com
SECRET_KEY=сгенерируйте-32-байтный-ключ
ENCRYPTION_KEY=сгенерируйте-fernet-ключ
```

**Генерация SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Генерация ENCRYPTION_KEY:**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Запуск через Docker Compose

```bash
docker-compose up -d --build
```

### 4. Проверка

```bash
# Статус контейнеров
docker-compose ps

# Логи бэкенда
docker-compose logs -f backend

# Логи бота
docker-compose logs -f bot
```

API будет доступен по адресу: `http://localhost:8000`  
Mini App: `http://localhost:3000`

---

## Настройка HTTPS (обязательно для Telegram Mini App)

Telegram требует HTTPS для Mini App. Используйте один из вариантов:

### Вариант A: Cloudflare Tunnel (бесплатно)

```bash
# Установите cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Туннель для Mini App
cloudflared tunnel --url http://localhost:80
```

### Вариант B: Let's Encrypt + nginx

```bash
# Установите certbot
sudo apt install certbot python3-certbot-nginx

# Получите сертификат
sudo certbot --nginx -d ваш-домен.com
```

Затем обновите `nginx/nginx.conf` с SSL конфигурацией.

---

## Настройка Telegram Bot

### Установка команд

Отправьте в @BotFather:
```
/setcommands
```
Затем выберите бота и введите:
```
start - Главное меню
help - Справка
shop - Открыть магазин
```

### Настройка Mini App

```
/newapp
```
Выберите бота и укажите URL вашего Mini App: `https://ваш-домен.com`

### Webhook (для продакшена)

```bash
curl -X POST "https://api.telegram.org/bot8241924602:AAHxqUWIR3II3JHliS22TM6kCw-PhKONh8A/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://ваш-домен.com/webhook"}'
```

---

## Структура проекта

```
1с хелпер/
├── backend/                    # FastAPI бэкенд
│   ├── api/                    # Эндпоинты
│   │   ├── auth.py             # Аутентификация через Telegram
│   │   ├── products.py         # Управление товарами
│   │   ├── stores.py           # Управление магазинами
│   │   ├── reports.py          # Отчёты
│   │   └── admin.py            # Панель администратора
│   ├── core/
│   │   └── security.py         # JWT, валидация Telegram initData
│   ├── database/
│   │   ├── models.py           # SQLAlchemy модели
│   │   └── connection.py       # Подключение к БД
│   ├── services/
│   │   ├── ai_service.py       # Claude AI интеграция
│   │   ├── ocr_service.py      # Tesseract OCR
│   │   ├── barcode_service.py  # pyzbar сканирование
│   │   └── cache_service.py    # Redis кэш
│   ├── integrations/
│   │   └── onec_integration.py # 1C OData клиент
│   ├── main.py                 # Точка входа
│   ├── config.py               # Настройки
│   ├── Dockerfile
│   └── requirements.txt
│
├── bot/                        # Telegram Bot (aiogram 3)
│   ├── handlers/
│   │   ├── start.py            # /start, /help
│   │   ├── menu.py             # Кнопки меню
│   │   └── admin.py            # Команды администратора
│   ├── keyboards/
│   │   └── main_keyboard.py    # ReplyKeyboard + WebApp кнопки
│   ├── middlewares/
│   │   └── auth_middleware.py  # Middleware авторизации
│   ├── main.py                 # Точка входа бота
│   ├── config.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── miniapp/                    # React Telegram Mini App
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx   # Главная страница
│   │   │   ├── Products.jsx    # Список товаров
│   │   │   ├── AddProduct.jsx  # Добавление товара (4 метода)
│   │   │   ├── UploadInvoice.jsx # Загрузка накладной
│   │   │   ├── Reports.jsx     # Отчёты
│   │   │   ├── Settings.jsx    # Настройки + 1С интеграция
│   │   │   └── Admin.jsx       # Панель администратора
│   │   ├── components/
│   │   │   ├── Layout.jsx
│   │   │   ├── BottomNav.jsx
│   │   │   ├── StatCard.jsx
│   │   │   └── ProductCard.jsx
│   │   ├── services/api.js     # Axios API клиент
│   │   ├── store/useStore.js   # Zustand state
│   │   └── App.jsx
│   ├── Dockerfile
│   └── package.json
│
├── nginx/
│   └── nginx.conf              # Обратный прокси
│
├── docker-compose.yml
├── .env
└── README.md
```

---

## База данных

| Таблица | Описание |
|---------|----------|
| `users` | Пользователи (Telegram ID, роль) |
| `stores` | Магазины (мультитенантность) |
| `integrations` | Настройки 1С (зашифрованный пароль) |
| `products_cache` | Кэш товаров (синхронизация с 1С) |
| `logs` | Лог действий пользователей |

---

## API эндпоинты

| Метод | URL | Описание |
|-------|-----|----------|
| POST | `/api/v1/auth/telegram` | Авторизация через Telegram initData |
| GET | `/api/v1/auth/me` | Текущий пользователь |
| GET | `/api/v1/stores/` | Список магазинов |
| POST | `/api/v1/stores/` | Создать магазин |
| GET | `/api/v1/products/{store_id}` | Список товаров |
| POST | `/api/v1/products/` | Создать товар |
| POST | `/api/v1/products/scan-barcode` | Сканировать штрих-код |
| POST | `/api/v1/products/recognize-photo` | Распознать фото |
| POST | `/api/v1/products/upload-invoice` | Загрузить накладную |
| GET | `/api/v1/reports/{store_id}/summary` | Сводка |
| GET | `/api/v1/admin/stats` | Статистика платформы |

Документация Swagger: `http://localhost:8000/docs` (только dev режим)

---

## Интеграция с 1С

Поддерживается подключение к 1С через стандартный OData REST интерфейс.

**Требования к 1С:**
- 1С:Предприятие 8.3.x
- Включённая публикация на веб-сервере (Apache/IIS)
- Включённый OData сервис: `odata/standard.odata/`
- HTTP Basic Auth

**Пример URL:**
```
http://192.168.1.100/УправлениеТорговлей/odata/standard.odata/
```

**Настройка в Mini App:**
1. Перейдите в Настройки → 1С
2. Введите URL, логин и пароль
3. Нажмите "Проверить подключение"

---

## Переменные окружения

| Переменная | Описание | Обязательно |
|-----------|----------|-------------|
| `BOT_TOKEN` | Токен Telegram бота | ✅ |
| `ADMIN_TELEGRAM_ID` | ID Telegram администратора | ✅ |
| `ANTHROPIC_API_KEY` | Ключ Claude API | ✅ |
| `SECRET_KEY` | JWT секретный ключ (32+ символа) | ✅ |
| `ENCRYPTION_KEY` | Fernet ключ для паролей 1С | ✅ |
| `MINIAPP_URL` | HTTPS URL Mini App | ✅ |
| `DATABASE_URL` | URL PostgreSQL | ✅ |
| `REDIS_URL` | URL Redis | ✅ |
| `WEBHOOK_URL` | URL для Telegram webhook | prod |

---

## Разработка (локально без Docker)

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Запустить PostgreSQL и Redis локально
# Обновить DATABASE_URL и REDIS_URL в .env

python -m backend.main
```

### Bot

```bash
cd bot
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m bot.main
```

### Mini App

```bash
cd miniapp
npm install
npm run dev
```

---

## Лицензия

MIT
