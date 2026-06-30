# Agent Lifecycle Backend API

FastAPI service that orchestrates dynamic agent lifecycle:

- Register a new persona configuration into Redis using separate record schemas for agent, goal, sensors, actuators, and prompt
- Keep system prompts synchronized in Redis using `system-prompts:<persona>:latest` and historized keys
- Instantiate a runtime container for that persona from the Redis configuration

## Run

From project root:

```bash
uvicorn client.backend.app:app --host 0.0.0.0 --port 8010
```

## Endpoints

### 1. Register agent configuration

`POST /api/agents/register`

Example body:

```json
{
  "persona": "my-deployer",
  "agent": {"apiVersion": "agents/v1", "kind": "Agent", "metadata": {"name": "my-deployer"}, "spec": {"goal": "my-deployer-goal", "sensors": [], "tools": [], "perform_planning": false}},
  "goal": {"apiVersion": "agents/v1", "kind": "Goal", "metadata": {"name": "my-deployer-goal"}, "spec": {"description": "You are an autonomous deployer.", "base_prompt": "Process requests."}},
  "sensors": {"apiVersion": "agents/v1", "kind": "Goal", "metadata": {"name": "my-deployer-sensors"}, "spec": []},
  "actuators": {"apiVersion": "agents/v1", "kind": "Actuators", "metadata": {"name": "my-deployer-actuators"}, "spec": {"mcp-servers": {}, "builtin-functions": []}},
  "metadata": {"owner": "platform"}
}
```

### 2. Instantiate agent container

`POST /api/agents/{persona}/instantiate`

Example body:

```json
{
  "force_recreate": true,
  "dry_run": false
}
```

This endpoint will:

1. Load latest section records from Redis
2. Materialize YAML files under `agent/personas/<persona>/`
3. Execute `client/backend/scripts/spawn_agent.sh`

## Redis Record Layout

The registry stores each section separately:

- `agent-records:agent:<persona>:latest`
- `agent-records:goal:<persona>:latest`
- `agent-records:sensors:<persona>:latest`
- `agent-records:actuators:<persona>:latest`
- `system-prompts:<persona>:latest`

Each hash also keeps a historized copy with a timestamp suffix and a one-month TTL.

## Notes

- The spawned container uses image `agent-generic:latest`.
- Container name is `<persona>-agent`.
- Runtime defaults mirror deployer-agent style env/volumes/secrets/network (`triton-ai-network`).

## Lifecycle Visualization

Agent lifecycle management flow is documented in:

- `management/backend/AGENT_LIFECYCLE_MANAGEMENT.mmd`
