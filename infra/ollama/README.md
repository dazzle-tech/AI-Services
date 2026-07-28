# Shared Ollama infrastructure for all AI services.
# Version pin: see infra/ollama/VERSION and infra/ollama/Dockerfile (ARG OLLAMA_VERSION).

## Docker Compose (single service + Ollama)

From any service directory:

```bash
cd SummarizationService
docker compose up -d
```

This starts the service API and a local Ollama container (`ai-services-ollama:0.32.2`).

## Docker Compose (Ollama only)

Run Ollama once and share it across services:

```bash
docker compose -f infra/ollama/docker-compose.yml up -d
```

Point services at the host Ollama with `OPENAI_BASE_URL=http://host.docker.internal:11434/v1` (Windows/Mac).

## Kubernetes

```bash
kubectl apply -f infra/ollama/k8s/
kubectl logs -f deployment/ollama -c pull-model
kubectl exec -it deployment/ollama -- ollama list
```

SummarizationService (and other pods) should use:

```env
OPENAI_BASE_URL=http://ollama:11434/v1
OPENAI_MODEL=qwen3:1.7b
OPENAI_API_KEY=ollama
```

## Version upgrades

1. Update `infra/ollama/VERSION`
2. Update `ARG OLLAMA_VERSION` default in `infra/ollama/Dockerfile`
3. Update `OLLAMA_VERSION` build arg and `image:` tag in `compose.fragment.yml` and `docker-compose.yml`
4. Update `image: ollama/ollama:…` in `infra/ollama/k8s/deployment.yaml`

All locations must stay in sync.

## Default models

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_MODELS` | `qwen3:1.7b` | Models pulled on Ollama startup |
| `OLLAMA_PORT` | `11434` | Host port for Ollama |

Medical image interpretation overrides `OLLAMA_MODELS` to also pull `qwen2.5vl:3b`.
