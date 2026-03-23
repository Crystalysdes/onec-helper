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

RUN pip install -e . --no-deps && \
    mkdir -p /app/data /app/uploads

EXPOSE 8000

COPY start.sh ./start.sh
RUN chmod +x ./start.sh

CMD ["./start.sh"]
