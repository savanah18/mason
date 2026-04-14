"""Prompt optimization retrieval tools."""

import json
import os
from typing import Any, Dict, List

import json5
import redis
from qwen_agent.tools.base import register_tool

from actions.tools.utils.traceability import (
    TRACEABILITY_PARAMS_ADD_ONS,
    MemoryTraceableTool,
    ToolExecStatus,
)


def parse_params(params: Any) -> Dict[str, Any]:
    if isinstance(params, dict):
        return params
    if not params:
        return {}
    try:
        parsed = json5.loads(params) if isinstance(params, str) else params
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _agents_enabled_for_optimization() -> List[str]:
    raw = os.getenv("AGENTS_ENABLED_FOR_OPTIMIZATION", "deployer,resiliency-optimizer")
    return [agent.strip() for agent in raw.split(",") if agent.strip()]


def _prompt_opt_batch_size() -> int:
    try:
        return max(1, int(os.getenv("PROMPT_OPT_NUM_BATCH", "16")))
    except Exception:
        return 16


def _resolve_target_personas(raw_persona: Any, enabled_personas: List[str]) -> List[str]:
    """Resolve a single optional persona filter against enabled personas."""
    if raw_persona is None:
        return enabled_personas

    if not isinstance(raw_persona, str):
        return []

    requested = raw_persona.strip()
    if not requested:
        return enabled_personas

    return [requested] if requested in set(enabled_personas) else []


def _get_latest_prompt_created_at(redis_client: redis.Redis, persona: str) -> str | None:
    """Return metadata.created_at for the persona's latest system prompt."""
    latest_key = f"system-prompts:{persona}:latest"
    prompt_data = redis_client.hgetall(latest_key) or {}
    metadata_raw = prompt_data.get("metadata")
    if not metadata_raw:
        return None

    try:
        metadata = json.loads(metadata_raw)
    except Exception:
        return None

    created_at = metadata.get("created_at")
    return created_at if isinstance(created_at, str) and created_at.strip() else None


@register_tool("prompt-optimization-retrieve-workflow-results")
class PromptOptimizationRetrieveWorkflowResults(MemoryTraceableTool):
    """Retrieve unprocessed workflow results for prompt optimization."""

    tool_name = "prompt-optimization-retrieve-workflow-results"

    description = (
        "Retrieve workflow results for personas enabled for optimization where "
        "optimization.reference matches the latest system prompt created_at."
    )

    parameters = [
        {
            "name": "max_results",
            "type": "integer",
            "description": "Optional max number of workflows to retrieve (defaults to PROMPT_OPT_NUM_BATCH).",
            "required": False,
        },
        {
            "name": "persona",
            "type": "string",
            "description": "Optional single persona filter (must be one of AGENTS_ENABLED_FOR_OPTIMIZATION).",
            "required": False,
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        args = {}
        exec_id = None
        try:
            args = parse_params(params)
            exec_id = self._pre_call(self.tool_name, args)

            max_results = args.get("max_results", _prompt_opt_batch_size())
            try:
                max_results = max(1, int(max_results))
            except Exception:
                max_results = _prompt_opt_batch_size()

            enabled_agents = _agents_enabled_for_optimization()
            agents = _resolve_target_personas(args.get("persona"), enabled_agents)
            r = redis.Redis(host="redis", port=6379, decode_responses=True)

            retrieved_workflows: List[Dict[str, Any]] = []
            latest_prompt_created_at: Dict[str, str | None] = {
                persona: _get_latest_prompt_created_at(r, persona) for persona in agents
            }

            for persona in agents:
                if len(retrieved_workflows) >= max_results:
                    break

                key_pattern = f"workflow:*:{persona}:*"
                target_reference = latest_prompt_created_at.get(persona)
                for key in r.scan_iter(match=key_pattern):
                    if len(retrieved_workflows) >= max_results:
                        break

                    workflow = r.hgetall(key) or {}
                    optimization_raw = workflow.get("optimization")

                    include = False
                    if optimization_raw and target_reference:
                        try:
                            optimization = json.loads(optimization_raw)
                            include = optimization.get("reference") == target_reference
                        except Exception:
                            include = False

                    if not include:
                        continue

                    metadata = {}
                    try:
                        metadata = json.loads(workflow.get("metadata", "{}"))
                    except Exception:
                        metadata = {}

                    retrieved_workflows.append(
                        {
                            "key": key,
                            "persona": persona,
                            "latest_prompt_created_at": target_reference,
                            "workflow_id": metadata.get("workflow_id"),
                            "result": workflow.get("result", ""),
                        }
                    )

            workflow_result_history = [wf.get("result", "") for wf in retrieved_workflows]

            result = {
                "success": True,
                "latest_prompt_created_at": latest_prompt_created_at,
                "num_retrieved": len(retrieved_workflows),
                "workflow_result_history": workflow_result_history,
                "exec_id": exec_id,
            }

            self._post_call(exec_id, self.tool_name, args, ToolExecStatus.COMPLETED, result=result)
            return json.dumps(result, ensure_ascii=False)
            # return  None
        except Exception as exc:
            result = {
                "success": False,
                "error": str(exc),
                "exec_id": exec_id,
            }
            if exec_id is not None:
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
            return json.dumps(result, ensure_ascii=False)
