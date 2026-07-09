# Getting Started

Use this path when you want the standard agent stack with vLLM-backed serving.

## Prerequisites

- Docker and Docker Compose
- GPU access for the serving container
- Local env files: `.env.qwen3.5-4b-vllm` and `.env.prometheus`
- Secrets mounted as expected by `docker-compose.yml`:
  - `./.secrets/oci-registry`
  - `~/.kube/config`
  - `~/.google-app-token`

## Start The Stack

From the project root:

```bash
docker compose --env-file .env.qwen3.5-4b-vllm --env-file .env.prometheus --profile standard --profile serving-vllm up --build
```

## What This Starts

- `main-vllm-server` for model serving
- `agent-manager` for agent lifecycle management
- `kubernetes-mcp-server` for cluster operations
- `kafka-server` for task/event routing
- Persona agents such as `chat-agent`, `deployer-agent`, `resiliency-optimizer-agent`, and `prompt-optimizer-agent`

## After Startup

- Open the VS Code operational interface to work with chat and worker agents.
- Use the agent manager API on port `8010` if you need to register or restart personas.
- Check the serving endpoint on the vLLM profile through the compose stack.

## Stop The Stack

```bash
docker compose --env-file .env.qwen3.5-4b-vllm --env-file .env.prometheus --profile standard --profile serving-vllm down
```

## Reproducibility Check

- Run `scripts/repro-check.sh` before starting the stack.
- Confirm the env files exist before starting the stack.
- Confirm `docker compose ps` shows `main-vllm-server`, `agent-manager`, `kafka-server`, and `kubernetes-mcp-server` after startup.
- Confirm the chat and worker agent entrypoints are `qwen-chat-agent.py` and `qwen-ops-agent.py`.
- Confirm `management/backend/scripts/spawn_agent.sh` no longer references another repository name.

## Related Docs

- [System Architecture](system-architecture.md)
- [Root README](../README.md)