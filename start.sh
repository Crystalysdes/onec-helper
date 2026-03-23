#!/bin/bash
set -e

echo "=== 1C Helper starting ==="
echo "DATABASE_URL: ${DATABASE_URL}"

# Start backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "Backend started (PID $BACKEND_PID)"

# Give backend 3 seconds to init DB
sleep 3

# Start bot (polling mode)
python -m bot.main &
BOT_PID=$!
echo "Bot started (PID $BOT_PID)"

# Restart either process if it dies
while true; do
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo "Backend died — restarting..."
        uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
        BACKEND_PID=$!
    fi
    if ! kill -0 $BOT_PID 2>/dev/null; then
        echo "Bot died — restarting..."
        python -m bot.main &
        BOT_PID=$!
    fi
    sleep 5
done
