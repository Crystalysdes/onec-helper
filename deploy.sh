#!/bin/bash
set -e
cd /app

echo "=== Pulling latest code ==="
git pull origin main

echo "=== Rebuilding backend ==="
docker compose -f docker-compose.timeweb.yml up -d --build

echo "=== Rebuilding miniapp ==="
cd miniapp
npm install --silent
npm run build
cd /app

echo "=== Done! dist at /app/miniapp/dist ==="
