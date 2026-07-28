# Pin Ollama version here — all services build from this Dockerfile.
ARG OLLAMA_VERSION=0.32.2
FROM ollama/ollama:${OLLAMA_VERSION}

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV OLLAMA_MODELS=qwen3:1.7b

EXPOSE 11434

ENTRYPOINT ["/docker-entrypoint.sh"]
