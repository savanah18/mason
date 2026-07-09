#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:?missing project root}"
PERSONA="${2:?missing persona}"
FORCE_RECREATE="${3:-true}"
DRY_RUN="${4:-false}"

CONTAINER_NAME="${PERSONA}-agent"
IMAGE="agent-generic:latest"
NETWORK_NAME="$(basename "$PROJECT_ROOT")_triton-ai-network"
HOST_MODEL_CKPT="${HOST_MODEL_CKPT:-/root/workspace/lnd/aiops/vlm/Qwen/Qwen2.5-7B-Instruct}"
OCI_REGISTRY_SECRET="${OCI_REGISTRY_SECRET:-$PROJECT_ROOT/.secrets/oci-registry}"
KUBECONFIG_PATH="${KUBECONFIG_PATH:-$HOME/.kube/config}"
GOOGLE_APP_TOKEN_PATH="${GOOGLE_APP_TOKEN_PATH:-$HOME/.google-app-token}"
GCLOUD_CONFIG_PATH="${GCLOUD_CONFIG_PATH:-$HOME/.config/gcloud}"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Image $IMAGE not found. Build agents first (docker compose build deployer-agent)." >&2
  exit 1
fi

if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
  docker network create "$NETWORK_NAME" >/dev/null
fi

if [[ "$FORCE_RECREATE" == "true" ]] && docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

echo "Inference Server Type: ${INFERENCE_SERVER_TYPE:-vllm}"

cmd=(
  docker run -d
  --name "$CONTAINER_NAME"
  --network "$NETWORK_NAME"
  --restart unless-stopped
  -e OCI_REGISTRY_SECRET=/run/secrets/oci-registry
  -e KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-kafka-server:9092}"
  -e KUBECONFIG=/run/secrets/kubernetes-config
  -e AGENT_MODE="${AGENT_MODE:-dev}"
  -e INFERENCE_SERVER_TYPE="${INFERENCE_SERVER_TYPE:-vllm}"
  -e PERSONA="$PERSONA"
  -e EMAIL_NOTIFICATION_ENABLED="${EMAIL_NOTIFICATION_ENABLED:-true}"
  -e EMAIL_APP_PASSWORD_FILE=/run/secrets/google-app-token
  -v "$PROJECT_ROOT/agent/qwen-ops-agent.py:/app/qwen-ops-agent.py:rw"
  -v "$PROJECT_ROOT/agent/personas:/app/personas:rw"
  -v "$PROJECT_ROOT/agent/templates:/app/templates:rw"
  -v "$PROJECT_ROOT/agent/actions:/app/actions:rw"
  -v "$PROJECT_ROOT/agent/memory:/app/memory:rw"
  -v "$PROJECT_ROOT/agent/notifications:/app/notifications:rw"
  -v "$HOST_MODEL_CKPT:/mnt/checkpoint:rw"
  -v "$OCI_REGISTRY_SECRET:/run/secrets/oci-registry:ro"
  -v "$KUBECONFIG_PATH:/run/secrets/kubernetes-config:ro"
  -v "$GOOGLE_APP_TOKEN_PATH:/run/secrets/google-app-token:ro"
  -v "$GCLOUD_CONFIG_PATH:/root/.config/gcloud:rw"
)

# if [[ -n "${HOST_MODEL_CKPT:-}" ]] && [[ -e "${HOST_MODEL_CKPT}" ]]; then
#   cmd+=( -v "${HOST_MODEL_CKPT}:/mnt/checkpoint:rw" )
# elif [[ -e "/root/workspace/lnd/aiops/vlm/Qwen/Qwen2.5-7B-Instruct" ]]; then
#   cmd+=( -v "/root/workspace/lnd/aiops/vlm/Qwen/Qwen2.5-7B-Instruct:/mnt/checkpoint:rw" )
# fi

# if [[ -e "/root/workspace/lnd/aiops/apps/newbie-app/agent/.secrets/oci-registry" ]]; then
#   cmd+=( -v "/root/workspace/lnd/aiops/apps/newbie-app/agent/.secrets/oci-registry:/run/secrets/oci-registry:ro" )
# fi
# if [[ -e "/root/.kube/config" ]]; then
#   cmd+=( -v "/root/.kube/config:/run/secrets/kubernetes-config:ro" )
# fi
# if [[ -e "/root/.google-app-token" ]]; then
#   cmd+=( -v "/root/.google-app-token:/run/secrets/google-app-token:ro" )
# fi
# if [[ -d "/root/.config/gcloud" ]]; then
#   cmd+=( -v "/root/.config/gcloud:/root/.config/gcloud:rw" )
# fi

cmd+=( "$IMAGE" python -u qwen-ops-agent.py )
# cmd+=( "$IMAGE" sleep 6000 )

if [[ "$DRY_RUN" == "true" ]]; then
  printf 'DRY_RUN: '
  printf '%q ' "${cmd[@]}"
  printf '\n'
  exit 0
fi

"${cmd[@]}"
