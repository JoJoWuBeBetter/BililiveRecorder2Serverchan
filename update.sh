#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-bililive-helper}"
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

cd "${PROJECT_ROOT}"

git pull
docker restart "${CONTAINER_NAME}"
docker logs --tail 50 "${CONTAINER_NAME}"
