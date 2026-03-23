@echo off
set PATH=%PATH%;C:\Users\%USERNAME%\.fly\bin

echo === Deploying to Fly.io ===
"C:\Users\%USERNAME%\.fly\bin\flyctl.exe" deploy --local-only
echo === Done ===
pause
