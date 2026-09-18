# Multi-arch image (amd64, arm64): homr on ONNX Runtime, FastAPI, static React frontend.
FROM node:22-alpine AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PP_DATA_DIR=/data PP_FRONTEND_DIR=/app/frontend/dist PP_ENGINE=homr PP_FALLBACK_ENGINE=none
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/partition_player ./partition_player
RUN uv pip install --system . && python -m homr.main --init
COPY --from=frontend /app/dist /app/frontend/dist
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "partition_player.api:app", "--host", "0.0.0.0", "--port", "8000"]
