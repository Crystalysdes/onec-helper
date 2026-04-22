---
description: Deploy to VPS (auto-handles SSH key setup, commit, push, build, health-check)
---

## Auto-deploy на net1c.ru

Один скрипт делает всё: коммит → push → SSH → docker rebuild → health-check.
При первом запуске попросит пароль сервера ОДИН раз (для установки SSH-ключа), потом работает без пароля.

// turbo
1. Запустить деплой:
```
powershell -ExecutionPolicy Bypass -File .\deploy.ps1
```

Опции:
- `.\deploy.ps1 -Message "fix: ..."` — свой commit message
- `.\deploy.ps1 -SkipCommit` — не коммитить локально, просто передеплоить текущий код на сервере
- `.\deploy.ps1 -VerifyOnly` — только health-check без деплоя

Скрипт сам:
1. Проверит наличие SSH-ключа, сгенерирует если нет
2. Проверит что ключ авторизован на сервере, запустит setup если нет
3. `git add -A && git commit && git push`
4. SSH на VPS → `git pull` → `docker compose down` → rebuild → up
5. Подождёт 8 секунд и проверит что `https://net1c.ru/` и `/api/v1/agent/info` отвечают 200
6. При ошибке — покажет последние 60 строк логов backend

Время: 5-8 минут (первый раз дольше).
