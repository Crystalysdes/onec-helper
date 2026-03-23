# Деплой 1С Хелпер

## Архитектура
- **Backend + Bot** → [JustRunMy.App](https://justrunmy.app) (бесплатно)
- **Miniapp (React)** → [Netlify](https://netlify.com) (бесплатно)

---

## Часть 1: Backend + Bot на JustRunMy.App

### Шаг 1 — Создай аккаунт
Зайди на https://justrunmy.app → Register

### Шаг 2 — Создай ZIP для загрузки
Запусти в PowerShell из папки `f:\1с хелпер`:
```powershell
Compress-Archive -Path backend, bot, Dockerfile, start.sh, requirements.prod.txt -DestinationPath deploy.zip -Force
```

### Шаг 3 — Создай новое приложение на JustRunMy.App
1. Dashboard → **New App**
2. Deploy method: **ZIP Upload**
3. Image: **Docker** (используем наш Dockerfile)
4. Загрузи `deploy.zip`

### Шаг 4 — Настрой переменные окружения
В разделе **Environment Variables** добавь:

| Переменная | Значение |
|---|---|
| `BOT_TOKEN` | `8241924602:AAHxqUWIR3II3JHliS22TM6kCw-PhKONh8A` |
| `BOT_USERNAME` | `oneshelperbot` |
| `ADMIN_TELEGRAM_ID` | `5504548686` |
| `SECRET_KEY` | `a7c9f3f2ffbc9d4ee6ba8aab0d6afe26966487fc45d0e5a7b33667df722974eb` |
| `ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` |
| `DATABASE_URL` | `sqlite+aiosqlite:////app/data/prod.db` |
| `ENVIRONMENT` | `production` |
| `LOG_LEVEL` | `INFO` |
| `ENCRYPTION_KEY` | `TDCJqf4_3BQwVcc33vhPv55MwbwfGvOX7lGuDzhOnpU=` |
| `TRIAL_DAYS` | `7` |
| `MINIAPP_URL` | *(заполнить после деплоя Netlify)* |

### Шаг 5 — Добавь HTTPS порт
В настройках приложения → **Ports** → Add port `8000` → получишь URL вида:
`https://your-app-name.justrunmy.app`

### Шаг 6 — Запусти приложение
Нажми **Start**. Логи должны показать:
```
Backend started
Bot started
```

---

## Часть 2: Miniapp на Netlify

### Шаг 1 — Создай аккаунт
Зайди на https://netlify.com → Sign Up (через GitHub)

### Шаг 2 — Собери miniapp для продакшена
Замени URL бэкенда в `miniapp/.env`:
```
VITE_API_URL=https://your-app-name.justrunmy.app/api/v1
```
Затем пересобери:
```powershell
& "C:\Program Files\nodejs\node.exe" "node_modules\vite\bin\vite.js" build
```

### Шаг 3 — Задеплой на Netlify
Вариант A — Drag & Drop (самый простой):
1. Открой https://app.netlify.com/drop
2. Перетащи папку `miniapp/dist` в браузер
3. Получишь URL вида: `https://amazing-name-123.netlify.app`

Вариант B — Netlify CLI:
```powershell
npx netlify-cli deploy --prod --dir miniapp/dist
```

### Шаг 4 — Обнови MINIAPP_URL
Зайди на JustRunMy.App → Environment Variables → обнови:
```
MINIAPP_URL=https://amazing-name-123.netlify.app
```
Перезапусти приложение.

---

## После деплоя: настрой бота в Telegram

В [@BotFather](https://t.me/BotFather):
1. `/setmenubutton` → выбери бота → укажи URL miniapp: `https://amazing-name-123.netlify.app`
2. Или через команду: отправь боту `/start` чтобы проверить что он отвечает

---

## Проверка
- Backend API: `https://your-app-name.justrunmy.app/health` → `{"status":"ok"}`
- Miniapp: `https://amazing-name-123.netlify.app` → открывается React приложение
- Бот: напиши `/start` в Telegram → должен ответить
