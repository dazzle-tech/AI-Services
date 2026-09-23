# Dockerfile for the MedAI Patient Assistant (chatbot-patient)
#
# BUILD CONTEXT IS THE REPO ROOT, not this folder, because the image also needs
# shared/medai-core. Build it via docker-compose (which sets `context: .`), or by hand:
#
#     docker build -f chatbot-patient/Dockerfile -t medai-chatbot-patient .
#
# The repo-root .dockerignore keeps the context small (no node_modules, data, services).
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Shared infrastructure package first — cached across most rebuilds.
COPY shared/medai-core /opt/medai-core
RUN pip install --upgrade pip && \
    pip install /opt/medai-core

COPY chatbot-patient/requirements.txt .
RUN pip install -r requirements.txt

COPY chatbot-patient/ .

# Prompts_patient.md and Services.txt are bind-mounted read-only at /app by
# docker-compose, so they stay canonical at the repo root.

RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8030

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8030/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8030"]
