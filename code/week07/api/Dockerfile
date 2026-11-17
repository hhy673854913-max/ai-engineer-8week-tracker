FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ ./requirements/
RUN pip install -r requirements/base.txt -r requirements/api.txt

COPY code/ ./code/
COPY data/ ./data/
COPY config.yaml ./

RUN useradd -m app && chown -R app:app /app
USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s CMD curl -f http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "code.week07.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
