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
        return max(1, int(os.getenv("PROMPT_OPT_NUM_BATCH", "8")))
    except Exception:
        return 8


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


@register_tool("prompt-optimization-retrieve-workflows")
class PromptOptimizationRetrieveWorkflows(MemoryTraceableTool):
    """Retrieve workflow IDs for prompt optimization."""

    tool_name = "prompt-optimization-retrieve-workflows"

    description = (
        "Retrieve workflow IDs for personas enabled for optimization where "
        "optimization.reference matches either an explicit reference or the latest system prompt created_at."
    )

    parameters = [
        {
            "name": "persona",
            "type": "string",
            "description": "Optional single persona filter (must be one of AGENTS_ENABLED_FOR_OPTIMIZATION).",
            "required": True,
        },
        {
            "name": "reference",
            "type": "string",
            "description": "Optional optimization reference filter. Defaults to latest_prompt_created_at for each persona.",
            "required": False,
        },
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

            enabled_agents = _agents_enabled_for_optimization()
            agents = _resolve_target_personas(args.get("persona"), enabled_agents)
            r = redis.Redis(host="redis", port=6379, decode_responses=True)
            requested_reference = f'system-prompts:{args.get("persona")}:{args.get("reference")}'
            if not isinstance(requested_reference, str):
                requested_reference = None
            elif not requested_reference.strip():
                requested_reference = None
            else:
                requested_reference = requested_reference.strip()

            workflow_ids: List[str] = []
            latest_prompt_created_at: Dict[str, str | None] = {
                persona: _get_latest_prompt_created_at(r, persona) for persona in agents
            }
            effective_reference: Dict[str, str | None] = {
                persona: requested_reference or latest_prompt_created_at.get(persona)
                for persona in agents
            }

            for persona in agents:
                if len(workflow_ids) >= max_results:
                    break

                key_pattern = f"workflow:*:{persona}:*"
                target_reference = effective_reference.get(persona)
                for key in r.scan_iter(match=key_pattern):
                    if len(workflow_ids) >= max_results:
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

                    metadata: Dict[str, Any] = {}
                    try:
                        metadata = json.loads(workflow.get("metadata", "{}"))
                    except Exception:
                        metadata = {}

                    workflow_id = metadata.get("workflow_id")
                    if isinstance(workflow_id, str) and workflow_id.strip():
                        workflow_ids.append(workflow_id)

            result = {
                "success": True,
                "requested_reference": requested_reference,
                "latest_prompt_created_at": latest_prompt_created_at,
                "effective_reference": effective_reference,
                "num_retrieved": len(workflow_ids),
                "workflow_ids": workflow_ids,
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


@register_tool("prompt-optimization-retrieve-workflow-result")
class PromptOptimizationRetrieveWorkflowResult(MemoryTraceableTool):
    """Retrieve workflow result by workflow_id."""

    tool_name = "prompt-optimization-retrieve-workflow-result"

    description = "Retrieve workflow result by workflow_id for prompt optimization."

    parameters = [
        {
            "name": "workflow_id",
            "type": "string",
            "description": "Workflow id to retrieve.",
            "required": True,
        },
        {
            "name": "persona",
            "type": "string",
            "description": "Optional persona filter (must be one of AGENTS_ENABLED_FOR_OPTIMIZATION).",
            "required": False,
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        args = {}
        exec_id = None
        try:
            args = parse_params(params)
            exec_id = self._pre_call(self.tool_name, args)

            workflow_id = args.get("workflow_id")
            if not isinstance(workflow_id, str) or not workflow_id.strip():
                raise ValueError("workflow_id is required and must be a non-empty string")
            workflow_id = workflow_id.strip()

            enabled_agents = _agents_enabled_for_optimization()
            agents = _resolve_target_personas(args.get("persona"), enabled_agents)
            if not agents:
                result = {
                    "success": True,
                    "workflow_id": workflow_id,
                    "found": False,
                    "result": None,
                    "exec_id": exec_id,
                }
                self._post_call(exec_id, self.tool_name, args, ToolExecStatus.COMPLETED, result=result)
                return json.dumps(result, ensure_ascii=False)

            r = redis.Redis(host="redis", port=6379, decode_responses=True)

            matched_key: str | None = None
            matched_persona: str | None = None
            matched_workflow: Dict[str, Any] | None = None

            for persona in agents:
                key_pattern = f"workflow:*:{persona}:*"
                for key in r.scan_iter(match=key_pattern):
                    workflow = r.hgetall(key) or {}
                    metadata: Dict[str, Any] = {}
                    try:
                        metadata = json.loads(workflow.get("metadata", "{}"))
                    except Exception:
                        metadata = {}

                    current_id = metadata.get("workflow_id")
                    if isinstance(current_id, str) and current_id == workflow_id:
                        matched_key = key
                        matched_persona = persona
                        matched_workflow = workflow
                        break
                if matched_workflow is not None:
                    break

            matched_result: str | None = None
            if matched_workflow is not None:
                raw_result = matched_workflow.get("result")
                matched_result = raw_result if isinstance(raw_result, str) else None

            result = {
                "success": True,
                "workflow_id": workflow_id,
                "found": matched_workflow is not None,
                "persona": matched_persona,
                "key": matched_key,
                "result": matched_result,
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


@register_tool("prompt-optimization-retrieve-system-prompt")
class PromptOptimizationRetrieveSystemPrompt(MemoryTraceableTool):
    """Retrieve a persona system prompt by explicit reference or latest."""

    tool_name = "prompt-optimization-retrieve-system-prompt"

    description = (
        "Retrieve system prompt text from Redis key "
        "system-prompts:<persona>:<reference-or-latest> using hash field 'prompt'."
    )

    parameters = [
        {
            "name": "persona",
            "type": "string",
            "description": "Target persona to retrieve system prompt for.",
            "required": True,
        },
        {
            "name": "reference",
            "type": "string",
            "description": "Optional prompt reference. Defaults to 'latest' when omitted.",
            "required": False,
        },
    ] + TRACEABILITY_PARAMS_ADD_ONS

    def call(self, params: str, **kwargs) -> str:
        args = {}
        exec_id = None
        try:
            args = parse_params(params)
            exec_id = self._pre_call(self.tool_name, args)

            persona = args.get("persona")
            if not isinstance(persona, str) or not persona.strip():
                raise ValueError("persona is required and must be a non-empty string")
            persona = persona.strip()

            enabled_agents = _agents_enabled_for_optimization()
            if persona not in set(enabled_agents):
                raise ValueError(
                    f"persona '{persona}' is not enabled for optimization: {enabled_agents}"
                )

            requested_reference = f'system-prompts:{args.get("persona")}:{args.get("reference")}'
            if not isinstance(requested_reference, str) or not requested_reference.strip():
                requested_reference = None
            else:
                requested_reference = requested_reference.strip()

            effective_reference = requested_reference or "latest"
            key = f"system-prompts:{persona}:{effective_reference}"

            r = redis.Redis(host="redis", port=6379, decode_responses=True)
            prompt_data = r.hgetall(key) or {}

            prompt_text = prompt_data.get("prompt")
            found = isinstance(prompt_text, str) and bool(prompt_text.strip())

            metadata: Dict[str, Any] | None = None
            metadata_raw = prompt_data.get("metadata")
            if isinstance(metadata_raw, str) and metadata_raw.strip():
                try:
                    parsed = json.loads(metadata_raw)
                    if isinstance(parsed, dict):
                        metadata = parsed
                except Exception:
                    metadata = None

            result = {
                "success": True,
                "persona": persona,
                "requested_reference": requested_reference,
                "effective_reference": effective_reference,
                "key": key,
                "found": found,
                "prompt": prompt_text if found else None,
                "metadata": metadata,
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
