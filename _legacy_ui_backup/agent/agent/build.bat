@echo off
REM Build standalone .exe for Windows via PyInstaller
REM Run from `agent/` folder

where python >nul 2>nul
if errorlevel 1 (
  echo Python not found in PATH.
  exit /b 1
)

python -m pip install --quiet --upgrade pyinstaller
python -m pyinstaller --onefile --name net1c-agent --noconfirm ^
  --hidden-import playwright.sync_api ^
  --collect-all playwright ^
  main.py

echo.
echo Build finished. Output: dist\net1c-agent.exe
echo Remember: on target machine run `playwright install chromium` once.
