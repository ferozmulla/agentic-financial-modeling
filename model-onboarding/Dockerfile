FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/* \
    && groupadd -r onboarder && useradd -r -g onboarder -d /app onboarder

COPY portfolio-assessment /app/portfolio-assessment
COPY model-onboarding/pyproject.toml model-onboarding/README.md /app/model-onboarding/
COPY model-onboarding/src /app/model-onboarding/src
COPY model-onboarding/sandbox_bundle /app/model-onboarding/sandbox_bundle
COPY model-onboarding/skills /app/model-onboarding/skills

RUN pip install --no-cache-dir /app/portfolio-assessment /app/model-onboarding \
    && chown -R onboarder:onboarder /app

USER onboarder

EXPOSE 8080

CMD ["uvicorn", "model_onboarding.mcp_app:app", "--host", "0.0.0.0", "--port", "8080"]
