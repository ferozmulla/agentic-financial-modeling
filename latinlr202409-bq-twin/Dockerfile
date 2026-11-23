FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

RUN groupadd --system appgroup && useradd --system --gid appgroup --create-home appuser

COPY requirements.txt pyproject.toml README.md /app/
COPY src /app/src
COPY scripts /app/scripts
COPY skills /app/skills

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-deps .

USER appuser
EXPOSE 8080

CMD ["uvicorn", "latinlr202409_bq_twin.mcp_app:app", "--host", "0.0.0.0", "--port", "8080"]
