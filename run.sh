#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-bililive-base:py39-ffmpeg}"
CONTAINER_NAME="${CONTAINER_NAME:-bililive-helper}"
HOST_PORT="${HOST_PORT:-18888}"
APP_PORT="${APP_PORT:-8000}"
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "${PROJECT_ROOT}/data" "${PROJECT_ROOT}/videos"

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

docker run -d \
  --name "${CONTAINER_NAME}" \
  --restart always \
  --env-file "${PROJECT_ROOT}/.env" \
  -p "${HOST_PORT}:${APP_PORT}" \
  -v "${PROJECT_ROOT}:/app" \
  -v "${PROJECT_ROOT}/data:/app/data" \
  -v "${PROJECT_ROOT}/videos:/app/videos" \
  "${IMAGE_NAME}" \
  /bin/sh -c "gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${APP_PORT} --timeout 300"

echo "容器已启动: ${CONTAINER_NAME}"
echo "访问地址: http://127.0.0.1:${HOST_PORT}"
