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

# Keep backend alive
wait $BACKEND_PID
