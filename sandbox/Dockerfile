# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    HOME=/tmp/datavision-home

WORKDIR /srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       r-base-core \
       r-cran-jsonlite \
       r-cran-ggplot2 \
       r-cran-dplyr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin sandbox
COPY app ./app
RUN chown -R sandbox:sandbox /srv

USER sandbox

EXPOSE 8090
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
