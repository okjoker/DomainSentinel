# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — build the React/TS SPA
# ---------------------------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — Python runtime serving the API and the built SPA in one container
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    STATIC_DIR=/app/static \
    BLOB_LOCAL_DIR=/app/data/blobs \
    DATABASE_URL=sqlite+aiosqlite:////app/data/domainsentinel.db \
    PORT=8080
WORKDIR /app

# Install runtime deps + the GCP extras so switching to Postgres/GCS is a pure
# config change (set DATABASE_URL / BLOB_BACKEND) with no image rebuild.
COPY backend/requirements.txt backend/requirements-gcp.txt ./
RUN pip install -r requirements.txt -r requirements-gcp.txt

COPY backend/app ./app
COPY --from=frontend /frontend/dist ./static
RUN mkdir -p /app/data/blobs

EXPOSE 8080
# Cloud Run injects $PORT; defaults to 8080 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
