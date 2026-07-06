FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY output_schema.json .
COPY medical_terms_guide.txt .
COPY rag_data/ ./rag_data/
COPY app/ ./app/

RUN mkdir -p /app/output

EXPOSE 8024

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8024/api/v1/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8024"]
