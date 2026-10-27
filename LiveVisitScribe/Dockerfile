# Dockerfile for LiveVisitScribe (live transcript WebSocket, port 8037).
# Build from this folder: docker build -t live-visit-scribe .
# No ffmpeg: the browser sends raw int16 PCM. Speech is OpenAI gpt-live-transcribe.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOST=0.0.0.0 \
    PORT=8037

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8037

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8037/api/v1/health')" || exit 1

CMD ["python", "main.py"]
