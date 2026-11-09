FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/src \
    BRAZIL_POWER_CLOUD_BACKEND=true \
    PORT=8080

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY seed/ ./seed/
COPY data/fixtures/ ./data/fixtures/
COPY migrations/ ./migrations/
COPY src/ ./src/

RUN mkdir -p /tmp/data/snapshots /tmp/data/bigquery_sink /tmp/brazil_power_exports /tmp/brazil_power_artifacts /tmp/brazil_power_sessions && \
    useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app /tmp/data /tmp/brazil_power_exports /tmp/brazil_power_artifacts /tmp/brazil_power_sessions
USER appuser

EXPOSE 8080

CMD ["sh", "-c", "uvicorn src.api.main:app --host ${CLOUD_RUN_HOST:-0.0.0.0} --port ${PORT:-8080}"]
