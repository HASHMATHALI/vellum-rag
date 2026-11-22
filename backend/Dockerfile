# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

# Exact, CPU-only dependency set (no CUDA wheels). See requirements.lock header for how it is generated.
COPY requirements.txt requirements.lock ./
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.lock

# Bake the embedding and reranker models into the image so containers start offline and fast.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

COPY app ./app

# Run as an unprivileged user; only the uploads directory is writable.
RUN useradd --system --uid 10001 --home /app vellum \
 && mkdir -p /app/uploads && chown -R vellum:vellum /app/uploads
USER vellum

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    ENVIRONMENT=production \
    UPLOAD_DIR=/app/uploads \
    LOG_FILE= \
    LOG_JSON=true \
    PORT=8000 \
    WEB_CONCURRENCY=2

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health', timeout=4)"

# Gunicorn supervises uvicorn workers (restarts crashed workers, graceful shutdown). $PORT is honoured for PaaS hosts.
CMD ["sh", "-c", "exec gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY} -b 0.0.0.0:${PORT} --timeout 180 --graceful-timeout 30 --forwarded-allow-ips='*' --access-logfile -"]
