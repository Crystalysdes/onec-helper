@echo off
cd /d "%~dp0"
set PYTHONPATH=%~dp0
echo Starting 1C Helper Backend...
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
pause
