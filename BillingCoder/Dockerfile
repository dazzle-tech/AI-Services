FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY coding_edit_rules.json .
COPY medical_necessity_policies.json .
COPY billing_data_guide.txt .
COPY output_schema.json .
COPY coding_seed_terms.json .
COPY app/ ./app/

RUN mkdir -p /app/output /app/rag_db

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/api/v1/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
