# Dockerfile for ConvoVoiceAgent.
# python main.py starts bundled ConvoScribe (8026) and SystemDisplayPlugin (8031)
# when they are not already listening, then serves this agent on 8036.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8036 \
    CONVOSCRIBE_BASE_URL=http://127.0.0.1:8026 \
    SYSTEM_DISPLAY_BASE_URL=http://127.0.0.1:8031

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8036 8026 8031

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8036/api/v1/health')" || exit 1

CMD ["python", "main.py"]
