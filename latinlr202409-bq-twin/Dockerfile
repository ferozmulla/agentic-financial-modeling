FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

RUN groupadd -r twinuser && useradd -r -g twinuser -d /app twinuser

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install --no-cache-dir --no-deps . && mkdir -p /app/runtime_exports && chown -R twinuser:twinuser /app

USER twinuser

EXPOSE 8080

CMD ["uvicorn", "latinlr202409_bq_twin.mcp_app:app", "--host", "0.0.0.0", "--port", "8080"]
