# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATAVISION_PROJECT_ROOT=/app
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY backend/app ./app
COPY compliance ./compliance
RUN groupadd --gid 10001 datavision \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin datavision \
    && mkdir -p /app/data/uploads /app/data/models /app/data/analyses /app/data/reports \
    && chown -R datavision:datavision /app
USER 10001:10001
EXPOSE 8005
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
