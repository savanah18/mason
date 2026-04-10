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


@register_tool("prompt-optimization-retrieve-workflow-results")
class PromptOptimizationRetrieveWorkflowResults(MemoryTraceableTool):
    """Retrieve unprocessed workflow results for prompt optimization."""

    tool_name = "prompt-optimization-retrieve-workflow-results"

    description = (
        "Retrieve workflow results for personas enabled for optimization where "
        "optimization.prompt is UNPROCESSED or optimization data does not exist."
    )

    parameters = [
        {
            "name": "max_results",
            "type": "integer",
            "description": "Optional max number of workflows to retrieve (defaults to PROMPT_OPT_NUM_BATCH).",
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

            agents = _agents_enabled_for_optimization()
            r = redis.Redis(host="redis", port=6379, decode_responses=True)

            retrieved_workflows: List[Dict[str, Any]] = []

            for persona in agents:
                if len(retrieved_workflows) >= max_results:
                    break

                key_pattern = f"workflow:*:{persona}:*"
                for key in r.scan_iter(match=key_pattern):
                    if len(retrieved_workflows) >= max_results:
                        break

                    workflow = r.hgetall(key) or {}
                    optimization_raw = workflow.get("optimization")

                    include = False
                    if not optimization_raw:
                        include = True
                    else:
                        try:
                            optimization = json.loads(optimization_raw)
                            include = optimization.get("prompt") == "UNPROCESSED"
                        except Exception:
                            include = True

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
                            "workflow_id": metadata.get("workflow_id"),
                            "result": workflow.get("result", ""),
                        }
                    )

            workflow_history = [wf.get("result", "") for wf in retrieved_workflows]

            result = {
                "success": True,
                "agents_enabled_for_optimization": agents,
                "num_retrieved": len(retrieved_workflows),
                "max_results": max_results,
                "workflow_history": workflow_history,
                "retrieved_workflows": retrieved_workflows,
                "exec_id": exec_id,
            }

            self._post_call(exec_id, self.tool_name, args, ToolExecStatus.COMPLETED, result=result)
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            result = {
                "success": False,
                "error": str(exc),
                "exec_id": exec_id,
            }
            if exec_id is not None:
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
            return json.dumps(result, ensure_ascii=False)
