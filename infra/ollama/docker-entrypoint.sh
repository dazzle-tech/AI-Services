#!/bin/sh
set -e

ollama serve &
pid=$!

echo "Waiting for Ollama to start..."
until ollama list >/dev/null 2>&1; do
  sleep 1
done

if [ -n "$OLLAMA_MODELS" ]; then
  for model in $(echo "$OLLAMA_MODELS" | tr ',' ' '); do
    echo "Pulling model: $model"
    ollama pull "$model"
  done
fi

echo "Ollama is ready."
wait "$pid"
