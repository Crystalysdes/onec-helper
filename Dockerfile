# ── Stage 1: build React frontend ────────────────────────────────────────────
FROM node:20-alpine AS frontend
WORKDIR /build
COPY miniapp/package.json miniapp/package-lock.json ./
RUN npm ci --prefer-offline
COPY miniapp/ ./
RUN npm run build

# ── Stage 2: Python backend ───────────────────────────────────────────────────
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libzbar0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app

COPY requirements_docker.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY bot/ ./bot/
COPY setup.py ./setup.py
COPY --from=frontend /build/dist ./static/

RUN pip install -e . --no-deps && \
    mkdir -p /app/data /app/uploads /app/logs

EXPOSE 8000

COPY start.sh ./start.sh
RUN chmod +x ./start.sh

CMD ["./start.sh"]
