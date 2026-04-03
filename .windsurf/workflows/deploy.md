---
description: Deploy to VPS directly from laptop (no GitHub Actions)
---

## Шаги деплоя на net1c.ru

**Первый раз только:** скопировать SSH ключ на VPS (один раз, потом не нужно)
// turbo
1. Запустить setup SSH:
```
.\setup-ssh.ps1
```
Введи пароль `kqT.Zv3kdcaqKG` когда спросит. После этого пароль больше не нужен.

**Каждый деплой:**

// turbo
2. Запустить деплой:
```
.\deploy.ps1
```

Скрипт сам: сделает git commit → git push → подключится к VPS → остановит контейнеры → пересоберёт образ → запустит → выведет "Deploy complete!"

Примерное время: 5-8 минут (первый раз дольше — npm install).
