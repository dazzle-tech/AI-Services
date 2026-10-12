# Dockerfile for the radiology STT service.
# Build from this folder: docker build -t stt-service .
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOST=0.0.0.0 \
    PORT=8027

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY api/ .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8027

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8027/api/v1/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8027"]
