@echo off
cd /d C:\Users\Миллиардер\Desktop\onec-helper
git add .
git commit -m "update"
git push origin main
echo.
echo ✅ Pushed! GitHub Actions запустит деплой автоматически (~47 сек)
pause
