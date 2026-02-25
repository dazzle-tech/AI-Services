#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="OCR Parsing Service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not in PATH."
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "Error: docker compose (or docker-compose) is not available."
  exit 1
fi

if [ ! -f ".env" ]; then
  echo "Warning: .env file not found in $SCRIPT_DIR."
fi

echo "Deploying $SERVICE_NAME..."
"${COMPOSE_CMD[@]}" down --remove-orphans
"${COMPOSE_CMD[@]}" up -d --build
"${COMPOSE_CMD[@]}" ps

echo "Deployment complete for $SERVICE_NAME."
