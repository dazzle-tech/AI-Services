#!/bin/bash
# Helper script: build | stop | logs | restart
set -e

case "${1:-build}" in
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
    docker compose restart
    ;;
  *)
    echo "Usage: $0 {build|stop|logs|restart}"
    exit 1
    ;;
esac
