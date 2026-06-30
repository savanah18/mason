"""Prompt optimization retrieval tools."""

import json
import os
from datetime import datetime, timezone
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
    raw = os.getenv("AGENTS_ENABLED_FOR_OPTIMIZATION", "deployer,resiliency-optimizer,chat")
    return [agent.strip() for agent in raw.split(",") if agent.strip()]


def _prompt_opt_batch_size() -> int:
    try:
        return max(1, int(os.getenv("PROMPT_OPT_NUM_BATCH", "16")))
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


def _workflow_has_evaluations(workflow: Dict[str, Any]) -> bool:
    """Return True if workflow has a meaningful evaluations payload."""
    raw_evaluations = workflow.get("evaluations")
    if not isinstance(raw_evaluations, str) or not raw_evaluations.strip():
        return False

    try:
        parsed = json.loads(raw_evaluations)
        return parsed not in (None, {}, [], "")
    except Exception:
        return True


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
            persona_arg = args.get("persona")
            if not isinstance(persona_arg, str) or not persona_arg.strip():
                raise ValueError("persona is required and must be a non-empty string")
            persona = persona_arg.strip()
            if persona not in set(enabled_agents):
                raise ValueError(
                    f"persona '{persona}' is not enabled for optimization: {enabled_agents}"
                )

            r = redis.Redis(host="redis", port=6379, decode_responses=True)
            raw_reference = args.get("reference")
            if isinstance(raw_reference, str) and raw_reference.strip():
                requested_reference = raw_reference.strip()
            else:
                requested_reference = None

            workflow_ids: List[str] = []
            workflows_with_evaluations = 0
            latest_prompt_created_at = {
                persona: _get_latest_prompt_created_at(r, persona)
            }
            effective_reference = {
                persona: requested_reference or latest_prompt_created_at.get(persona)
            }

            target_reference = effective_reference.get(persona)
            key_pattern = f"workflow:*:{persona}:*"
            print("DEBUG",target_reference) 

            persona_eval_workflow_ids: List[str] = []
            persona_non_eval_workflow_ids: List[str] = []

            for key in r.scan_iter(match=key_pattern):
                workflow = r.hgetall(key) or {}
                optimization_raw = workflow.get("optimization")

                include = False
                if optimization_raw and target_reference:
                    try:
                        optimization = json.loads(optimization_raw)
                        include = optimization.get("reference") == f"system-prompts:{persona}:{target_reference}"
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
                    if _workflow_has_evaluations(workflow):
                        persona_eval_workflow_ids.append(workflow_id)
                    else:
                        persona_non_eval_workflow_ids.append(workflow_id)

            ordered_persona_ids = persona_eval_workflow_ids + persona_non_eval_workflow_ids
            selected_ids = ordered_persona_ids[:max_results]
            workflow_ids.extend(selected_ids)
            workflows_with_evaluations += min(len(persona_eval_workflow_ids), len(selected_ids))

            result = {
                "success": True,
                "requested_reference": requested_reference,
                "latest_prompt_created_at": latest_prompt_created_at,
                "effective_reference": effective_reference,
                "num_retrieved": len(workflow_ids),
                "num_with_evaluations": workflows_with_evaluations,
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
            evaluations_exists = False
            evaluations: Any = None
            if matched_workflow is not None:
                raw_result = matched_workflow.get("result")
                matched_result = raw_result if isinstance(raw_result, str) else None

                raw_evaluations = matched_workflow.get("evaluations")
                if isinstance(raw_evaluations, str) and raw_evaluations.strip():
                    evaluations_exists = True
                    try:
                        evaluations = json.loads(raw_evaluations)
                    except Exception:
                        evaluations = raw_evaluations

            result = {
                "success": True,
                "workflow_id": workflow_id,
                "found": matched_workflow is not None,
                "persona": matched_persona,
                "key": matched_key,
                "result": matched_result,
                "evaluations_exists": evaluations_exists,
                "evaluations": evaluations,
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

            requested_reference = f'system-prompts:{args.get("persona")}:{args.get("reference", "latest")}'
            if not isinstance(requested_reference, str) or not requested_reference.strip():
                requested_reference = None
            else:
                requested_reference = requested_reference.strip()

            effective_reference = requested_reference
            key = effective_reference

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
            
            feedback = prompt_data.get("feedback", "No feedback found.")

            result = {
                "success": True,
                "persona": persona,
                "requested_reference": requested_reference,
                "effective_reference": effective_reference,
                "key": key,
                "found": found,
                "prompt": prompt_text if found else None,
                "metadata": metadata,
                "feedback": feedback,
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


@register_tool("prompt-optimization-write-candidate-prompt")
class PromptOptimizationWriteCandidatePrompt(MemoryTraceableTool):
    """Write updated candidate prompt for a workflow into Redis."""

    tool_name = "prompt-optimization-write-candidate-prompt"

    description = (
        "Write candidate prompt data into Redis hash key "
        "prompt-optimization:candidate-prompts:<persona>:<workflow-id>."
    )

    parameters = [
        {
            "name": "persona",
            "type": "string",
            "description": "Target persona for the candidate prompt.",
            "required": True,
        },
        {
            "name": "workflow_id",
            "type": "string",
            "description": "Workflow identifier for the candidate prompt record.",
            "required": True,
        },
        {
            "name": "updated_prompt",
            "type": "string",
            "description": "Updated prompt text.",
            "required": True,
        },
        {
            "name": "original_prompt",
            "type": "string",
            "description": "Original prompt reference id.",
            "required": True,
        },
        {
            "name": "created_by",
            "type": "string",
            "description": "Creator tag. Defaults to 'prompt_optimizer'.",
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
            workflow_id = args.get("workflow_id")
            updated_prompt = args.get("updated_prompt")
            original_prompt = args.get("original_prompt")

            if not isinstance(persona, str) or not persona.strip():
                raise ValueError("persona is required and must be a non-empty string")
            persona = persona.strip()

            if not isinstance(workflow_id, str) or not workflow_id.strip():
                raise ValueError("workflow_id is required and must be a non-empty string")
            workflow_id = workflow_id.strip()

            if not isinstance(updated_prompt, str) or not updated_prompt.strip():
                raise ValueError("updated_prompt is required and must be a non-empty string")

            if not isinstance(original_prompt, str) or not original_prompt.strip():
                raise ValueError("original_prompt is required and must be a non-empty string")

            created_by = args.get("created_by", "prompt_optimizer")
            if not isinstance(created_by, str) or not created_by.strip():
                created_by = "prompt_optimizer"

            created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            key = f"prompt-optimization:candidate-prompts:{persona}:{workflow_id}"
            payload = {
                "updated_prompt": updated_prompt,
                "original_prompt": original_prompt,
                "created_at": created_at,
                "created_by": created_by.strip(),
            }

            r = redis.Redis(host="redis", port=6379, decode_responses=True)
            r.hset(key, mapping=payload)

            result = {
                "success": True,
                "key": key,
                "stored": payload,
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
