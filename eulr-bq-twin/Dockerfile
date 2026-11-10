FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EULR_TWIN_EXPORT_LOCAL_DIR=/app/runtime_exports \
    PORT=8080

WORKDIR /app

# Create non-root runtime user
RUN groupadd -r eulrtwin && useradd -r -g eulrtwin -d /app eulrtwin

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install --no-cache-dir --no-deps . && mkdir -p /app/runtime_exports && chown -R eulrtwin:eulrtwin /app

USER eulrtwin

EXPOSE 8080

CMD ["uvicorn", "eulr_bq_twin.mcp_app:app", "--host", "0.0.0.0", "--port", "8080"]
