FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8080

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p /tmp/bq_twin_exports /tmp/bq_twin_artifacts && \
    useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app /tmp/bq_twin_exports /tmp/bq_twin_artifacts
USER appuser

EXPOSE 8080

CMD ["sh", "-c", "uvicorn brazil_power_bq_twin.mcp_app:app --host ${CLOUD_RUN_HOST:-0.0.0.0} --port ${PORT:-8080}"]
