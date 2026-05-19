#!/usr/bin/env bash
# Helper to build, stop, log, or restart the Medical Imaging Assist container.
set -euo pipefail

CMD="${1:-help}"

case "$CMD" in
  build)
    docker compose build
    docker compose up -d
    ;;
  stop)
    docker compose down
    ;;
  logs)
    docker compose logs -f
    ;;
  restart)
    docker compose down
    docker compose up -d --build
    ;;
  help|*)
    echo "Usage: $0 {build|stop|logs|restart}"
    exit 1
    ;;
esac
