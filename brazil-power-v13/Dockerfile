FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY seed/ ./seed/
COPY data/fixtures/ ./data/fixtures/
COPY migrations/ ./migrations/
COPY src/ ./src/

RUN mkdir -p /tmp/data/snapshots /tmp/data/bigquery_sink && \
    useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app /tmp/data
USER appuser

EXPOSE 8080

CMD ["sh", "-c", "uvicorn src.api.main:app --host ${CLOUD_RUN_HOST:-0.0.0.0} --port ${PORT:-8080}"]
