# ── Stage 1: Build React frontend ────────────────────────────────────────────
FROM node:20-alpine AS frontend

WORKDIR /frontend
COPY miniapp/package*.json ./
RUN npm ci
COPY miniapp/ ./
RUN npm run build

# ── Stage 2: Python backend ───────────────────────────────────────────────────
FROM public.ecr.aws/docker/library/python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libzbar0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app

COPY requirements_docker.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY bot/ ./bot/
COPY setup.py ./setup.py

# Copy built React app from stage 1
COPY --from=frontend /frontend/dist ./static/

RUN pip install -e . --no-deps && \
    mkdir -p /app/data /app/uploads /app/logs

EXPOSE 8000

COPY start.sh ./start.sh
RUN chmod +x ./start.sh

CMD ["./start.sh"]
