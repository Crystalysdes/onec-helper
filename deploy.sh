#!/bin/bash
set -e

echo "=== Pulling latest code ==="
git pull origin main

echo "=== Rebuilding backend ==="
docker compose -f docker-compose.timeweb.yml up -d --build

echo "=== Rebuilding miniapp ==="
cd miniapp
npm install --silent
npm run build
cd ..

echo "=== Copying miniapp dist to nginx ==="
# Try common locations for nginx static root
NGINX_ROOT=""
for candidate in \
    /var/www/html \
    /usr/share/nginx/html \
    /app/static \
    /app/miniapp_dist; do
    if [ -d "$candidate" ]; then
        NGINX_ROOT="$candidate"
        break
    fi
done

if [ -n "$NGINX_ROOT" ]; then
    cp -r miniapp/dist/* "$NGINX_ROOT/"
    echo "Copied to $NGINX_ROOT"
else
    echo "WARNING: Could not find nginx root. Copy miniapp/dist/* manually."
    echo "Current dist files are at: $(pwd)/miniapp/dist/"
fi

echo "=== Done ==="
