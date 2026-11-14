# Blind Spot API. Build from the REPOSITORY ROOT (the image needs backend/ and data/):
#   docker build -f backend/Dockerfile -t blindspot-api .
#   docker run -p 8000:8000 --env-file .env blindspot-api
# Only the files copied below enter the image (.env, *.db and logs/ never do).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 \
    ALLOWED_ORIGINS=http://localhost:3000 \
    TRUSTED_PROXY_HOPS=0 \
    ENABLE_DOCS=0

RUN groupadd --system app && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --upgrade pip && pip install -r backend/requirements.txt

# Application code and the precomputed demo (the server has no SQLite DB; the demo is served from JSON).
COPY backend/*.py backend/
COPY data/demo_audit.json data/demo_profile.json data/demo_deals.json data/

# Read-only for the app user: it writes nothing at runtime.
RUN chown -R root:root /app && chmod -R a-w /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=4)"

# One worker: the per-IP rate limit is kept in process memory.
CMD ["sh", "-c", "exec uvicorn app:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-server-header"]
