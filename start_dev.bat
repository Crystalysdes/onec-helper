@echo off
echo Starting 1C Helper Dev Environment...

:: Kill old instances
echo Killing old instances on ports 8000 and 3000...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000 "') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":3000 "') do taskkill /F /PID %%a 2>nul
timeout /t 2 /nobreak >nul

:: Start backend (port 8000)
echo Starting backend on port 8000...
start "Backend :8000" cmd /k "cd /d f:\1с хелпер && set PYTHONPATH=f:\1с хелпер && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 3 /nobreak >nul

:: Start dev proxy (port 3000)
echo Starting dev proxy on port 3000...
start "Dev Proxy :3000" cmd /k "cd /d f:\1с хелпер && python dev_proxy.py"

echo.
echo Services started in separate windows.
echo Backend:   http://localhost:8000
echo Proxy:     http://localhost:3000
echo Miniapp:   https://soil-aerial-headlines-delivered.trycloudflare.com
pause
