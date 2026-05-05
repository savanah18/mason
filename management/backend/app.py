from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from .agent_registry import AgentRegistry
from .docker_runtime import (
    restart_agent_container,
    spawn_agent_container,
    terminate_agent_container,
)
from .models import AgentRegistrationRequest, InstantiateAgentRequest
from .persona_writer import write_persona_configs


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

app = FastAPI(title="Agent Lifecycle Orchestrator", version="0.1.0")
registry = AgentRegistry(redis_host=REDIS_HOST, redis_port=REDIS_PORT)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/agents/register")
def register_agent(request: AgentRegistrationRequest) -> dict:
    try:
        result = registry.register_agent(request.model_dump())
        return {
            "success": True,
            "message": "agent configuration registered",
            "result": result,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"registration failed: {exc}") from exc


@app.post("/api/agents/{persona}/instantiate")
def instantiate_agent(persona: str, request: InstantiateAgentRequest) -> dict:
    config = registry.load_latest_agent_config(persona)
    if not config:
        raise HTTPException(status_code=404, detail=f"No registered config for persona={persona}")

    records = config.get("records", {}) or {}
    agent_record = records.get("agent") or {}
    goal_record = records.get("goal") or {}
    sensors_record = records.get("sensors") or {}
    actuators_record = records.get("actuators") or {}

    agent_payload = agent_record.get("payload", config.get("agent", {}))
    goal_payload = goal_record.get("payload", config.get("goal", {}))
    sensors_payload = sensors_record.get("payload", config.get("sensors", {}))
    actuators_payload = actuators_record.get("payload", config.get("actuators", {}))

    try:
        written = write_persona_configs(
            base_dir=PROJECT_ROOT,
            persona=persona,
            configs={
                "agent": agent_payload,
                "goal": goal_payload,
                "sensors": sensors_payload,
                "actuators": actuators_payload,
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to materialize persona yaml: {exc}") from exc


    spawn_result = spawn_agent_container(
        project_root=PROJECT_ROOT,
        persona=persona,
        force_recreate=request.force_recreate,
        dry_run=request.dry_run,
    )

    status_code = 200 if spawn_result["success"] else 500
    if not spawn_result["success"]:
        raise HTTPException(status_code=status_code, detail=spawn_result)

    # update registry status to running
    try:
        registry.set_agent_status(persona, "running")
    except Exception:
        pass

    return {
        "success": True,
        "message": "agent instantiated",
        "persona": persona,
        "source_records": {
            "agent": agent_record,
            "goal": goal_record,
            "sensors": sensors_record,
            "actuators": actuators_record,
        },
        "written_files": [str(path.relative_to(PROJECT_ROOT)) for path in written],
        "spawn": spawn_result,
    }


@app.delete("/api/agents/{persona}")
def delete_agent(persona: str) -> dict:
    persona = (persona or "").strip()
    if not persona:
        raise HTTPException(status_code=400, detail="persona is required")

    try:
        # attempt to mark terminated, then terminate runtime and delete registry records
        try:
            registry.set_agent_status(persona, "terminated")
        except Exception:
            pass
        runtime_result = terminate_agent_container(persona, remove=True)
        result = registry.delete_agent(persona)
        return {
            "success": True,
            "message": "agent records deleted",
            "runtime": runtime_result,
            "result": result,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"deletion failed: {exc}") from exc


@app.post("/api/agents/{persona}/terminate")
def terminate_agent(persona: str) -> dict:
    persona = (persona or "").strip()
    if not persona:
      raise HTTPException(status_code=400, detail="persona is required")

    try:
        runtime_result = terminate_agent_container(persona, remove=False)
        status_code = 200 if runtime_result["success"] else 500
        if not runtime_result["success"]:
            raise HTTPException(status_code=status_code, detail=runtime_result)
        try:
            registry.set_agent_status(persona, "terminated")
        except Exception:
            pass
        return {
            "success": True,
            "message": "agent container terminated",
            "result": runtime_result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"termination failed: {exc}") from exc


@app.post("/api/agents/{persona}/restart")
def restart_agent(persona: str) -> dict:
    persona = (persona or "").strip()
    if not persona:
        raise HTTPException(status_code=400, detail="persona is required")

    try:
        runtime_result = restart_agent_container(persona)
        if not runtime_result.get("exists", True):
            raise HTTPException(status_code=404, detail=f"container not found for persona={persona}")
        status_code = 200 if runtime_result["success"] else 500
        if not runtime_result["success"]:
            raise HTTPException(status_code=status_code, detail=runtime_result)
        try:
            registry.set_agent_status(persona, "running")
        except Exception:
            pass
        return {
            "success": True,
            "message": "agent container restarted",
            "result": runtime_result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"restart failed: {exc}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("client.backend.app:app", host="0.0.0.0", port=8010, reload=False)
