# Dockerfile for LiveVisitScribe (live transcript WebSocket, port 8037).
# Build from this folder: docker build -t live-visit-scribe .
# No ffmpeg: the browser sends raw int16 PCM. libgomp1 is needed by the Whisper VAD runtime.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOST=0.0.0.0 \
    PORT=8037 \
    WHISPER_MODEL_CACHE=/models/whisper \
    HF_HOME=/models/hf

RUN apt-get update && \
    apt-get install -y --no-install-recommends libgomp1 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# /models holds the downloaded Whisper model; mount a volume there so it is fetched only once.
RUN useradd -m -u 1000 appuser && mkdir -p /models && chown -R appuser:appuser /app /models
USER appuser

EXPOSE 8037
VOLUME ["/models"]

# The first start downloads the Whisper model, so allow a long start period.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8037/api/v1/health')" || exit 1

CMD ["python", "main.py"]
