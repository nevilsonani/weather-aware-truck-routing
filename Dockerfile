# syntax=docker/dockerfile:1.7
# Single image serving the React SPA and the Django API from one origin (no CORS needed).

# --- 1. Build the frontend ------------------------------------------------------------------
# glibc-based image: Vite 8 / Rolldown, oxlint and TypeScript 7 ship native binaries.
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Runtime ------------------------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_ENV=production \
    FRONTEND_DIST_DIR=/app/frontend_dist
WORKDIR /app

COPY backend/requirements/ requirements/
RUN pip install -r requirements/base.txt

COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend_dist
RUN DJANGO_SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput \
    && useradd --create-home --uid 10001 app \
    && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health', timeout=4)"
# Threads: requests are I/O-bound (routing + weather APIs). Timeout covers worst-case upstreams.
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --threads ${GUNICORN_THREADS:-8} --timeout 90 --access-logfile -"]
