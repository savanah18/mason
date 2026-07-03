#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

ENV_FILES=(
  ".env.qwen3.5-4b-vllm"
  ".env.prometheus"
)

SECRET_FILES=(
  ".secrets/oci-registry"
  "$HOME/.kube/config"
  "$HOME/.google-app-token"
)

EXPECTED_SERVICES=(
  "main-vllm-server"
  "agent-manager"
  "kafka-server"
  "kubernetes-mcp-server"
  "chat-agent"
  "deployer-agent"
  "resiliency-optimizer-agent"
  "prompt-optimizer-agent"
)

COMPOSE_ARGS=(
  --env-file .env.qwen3.5-4b-vllm
  --env-file .env.prometheus
  --profile standard
  --profile serving-vllm
)

fail() {
  echo "[repro-check] $*" >&2
  exit 1
}

echo "[repro-check] project root: $PROJECT_ROOT"

for file in "${ENV_FILES[@]}"; do
  [[ -f "$file" ]] || fail "missing required env file: $file"
done

for file in "${SECRET_FILES[@]}"; do
  [[ -e "$file" ]] || fail "missing required secret or host file: $file"
done

mapfile -t services < <(docker compose "${COMPOSE_ARGS[@]}" config --services)

for expected in "${EXPECTED_SERVICES[@]}"; do
  if ! printf '%s\n' "${services[@]}" | grep -Fxq "$expected"; then
    fail "missing compose service: $expected"
  fi
done

echo "[repro-check] required env files found"
echo "[repro-check] required secrets found"
echo "[repro-check] compose services available"
echo "[repro-check] ok"