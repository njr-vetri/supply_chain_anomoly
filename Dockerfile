# Optional local container packaging for the API; not a deployment recipe.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.lock ./requirements.lock
RUN python -m pip install --no-cache-dir -r requirements.lock

COPY api ./api
COPY src ./src
COPY config ./config
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY docs/API_CONTRACT.md ./docs/API_CONTRACT.md

RUN mkdir -p /app/data/processed
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
