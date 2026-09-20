# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATAVISION_PROJECT_ROOT=/app
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY backend/app ./app
COPY compliance ./compliance
RUN mkdir -p /app/data/uploads /app/data/models /app/data/analyses /app/data/reports
EXPOSE 8005
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
