@echo off
echo === Pushing to GitHub (auto-deploy to Render) ===
"C:\Program Files\Git\bin\git.exe" add -A
"C:\Program Files\Git\bin\git.exe" commit -m "Update %date% %time%"
"C:\Program Files\Git\bin\git.exe" push
echo === Done! Render will deploy automatically in ~2 min ===
pause
