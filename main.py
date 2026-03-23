import sys
import os
import subprocess

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

# Auto-install dependencies (JustRunMy.App activates venv but doesn't pip-install)
_req = os.path.join(_ROOT, "requirements.txt")
if os.path.exists(_req):
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", _req, "-q", "--no-warn-script-location"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[warn] pip install had issues:\n{result.stderr[-500:]}", flush=True)

import asyncio


async def run_all():
    import uvicorn
    from backend.main import app
    from bot.main import main as bot_main

    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    await asyncio.gather(
        server.serve(),
        bot_main(),
    )


if __name__ == "__main__":
    asyncio.run(run_all())
