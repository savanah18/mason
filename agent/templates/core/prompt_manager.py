import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import redis
import json5
import yaml
from qwen_agent.tools.base import register_tool

from actions.tools.utils.traceability import (
	TRACEABILITY_PARAMS_ADD_ONS,
	MemoryTraceableTool,
	ToolExecStatus,
)


def parse_params(params: Any) -> Dict[str, Any]:
	"""Safely parse tool params from dict or JSON string."""
	if isinstance(params, dict):
		return params
	if not params:
		return {}
	try:
		parsed = json5.loads(params) if isinstance(params, str) else params
		return parsed if isinstance(parsed, dict) else {}
	except Exception:
		return {}


class PromptUpdater:
	"""Historize persona system prompts in Redis and track the latest version."""

	ONE_MONTH_TTL_SECONDS = 30 * 24 * 60 * 60

	def __init__(self, redis_host: str = "redis", redis_port: int = 6379):
		self.redis_host = redis_host
		self.redis_port = redis_port

	def update_system_prompt(self, persona: str, system_prompt: Optional[str] = None) -> bool:
		"""
		Ensure Redis stores the latest system prompt and a historized copy.

		Workflow:
		- Reads current system prompt from personas/<persona>/goal.yaml (spec.description)
		- Checks Redis key system-prompts:<persona>:latest
		- If missing: writes latest and system-prompts:<persona>:<datetime> (1 month TTL)
		- If present and changed: updates latest and writes new historized key (1 month TTL)

		Returns:
			bool: True when operation succeeds, False on failures.
		"""
		result = self.update_system_prompt_with_status(persona=persona, system_prompt=system_prompt)
		return bool(result.get("success", False))

	def update_system_prompt_with_status(self, persona: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
		"""Update latest/historized prompt and return structured status details."""
		try:

			current_prompt, remarks, feedback = system_prompt or self._load_system_prompt_from_goal_yaml(persona)
			current_prompt = (current_prompt or "").strip()
			if not current_prompt:
				print(f"[PromptUpdater] Empty prompt for persona={persona}; skipping update")
				return {
					"success": False,
					"updated": False,
					"reason": "empty-prompt",
					"persona": persona,
					"latest_key": None,
				}

			client = self._redis_client()
			latest_key = f"system-prompts:{persona}:latest"
			historized_key = f"system-prompts:{persona}:{self._now_key_suffix()}"

			try:
				existing_prompt = client.hgetall(latest_key)
				print(f"[PromptUpdater] Fetched existing prompt for persona={persona}")
			except Exception as exc:
				print(f"[PromptUpdater] Error fetching existing prompt for persona={persona}: {exc}")
				# existing_prompt = None

			if not existing_prompt.get("prompt"):
				print("DEBUG", latest_key, historized_key)
				mapping = {
					"prompt": current_prompt,
					"metadata": json.dumps({
						"persona": persona,
						"created_at": historized_key,
					}),
					"remarks": json.dumps(remarks),
					"feedback": json.dumps(feedback),
				}
				client.hset(latest_key,mapping=mapping)
				client.hset(historized_key,mapping=mapping)
				client.expire(historized_key, self.ONE_MONTH_TTL_SECONDS)
				print(f"[PromptUpdater] Created latest and historized prompt for persona={persona}")
				return {
					"success": True,
					"updated": True,
					"reason": "created",
					"persona": persona,
					"latest_key": historized_key,
				}

			if existing_prompt["prompt"] != current_prompt:
				mapping = {
					"prompt": current_prompt,
					"metadata": json.dumps({
						"persona": persona,
						"created_at": historized_key,
					}),
					"remarks": json.dumps(remarks),
					"feedback": json.dumps(feedback),
				}
				client.hset(latest_key,mapping=mapping)
				client.hset(historized_key,mapping=mapping)
				client.expire(historized_key, self.ONE_MONTH_TTL_SECONDS)
				print(f"[PromptUpdater] Updated latest and historized prompt for persona={persona}")
				return {
					"success": True,
					"updated": True,
					"reason": "updated",
					"persona": persona,
					"latest_key": historized_key,
				}

			print(f"[PromptUpdater] No prompt change detected for persona={persona}")
			return {
				"success": True,
				"updated": False,
				"reason": "no-change",
				"persona": persona,
				"latest_key": json.loads(existing_prompt["metadata"])["created_at"] if "metadata" in existing_prompt else None,
			}
		except Exception as exc:
			print(f"[PromptUpdater] Failed to update prompt for persona={persona}: {exc}")
			return {
				"success": False,
				"updated": False,
				"reason": str(exc),
				"persona": persona,
				"latest_key": None,
			}

	def _load_system_prompt_from_goal_yaml(self, persona: str) -> Tuple[str, dict, str]:
		base_dir = Path(__file__).resolve().parents[2]
		filename = "prompts.yaml" if persona == "chat" else "goal.yaml"
		goal_path = base_dir / "personas" / persona / filename

		with open(goal_path, "r", encoding="utf-8") as stream:
			payload = yaml.safe_load(stream) or {}

		prompt = (payload.get("spec", {}) or {}).get("description", "") or payload.get("system", "")
		remarks = payload.get("spec", {}).get("remarks", {}) or payload.get("remarks", {})
		feedback = payload.get("spec", {}).get("feedback", "") or payload.get("feedback", "")

		return prompt, remarks, feedback

	def _redis_client(self) -> redis.Redis:
		host = os.getenv("REDIS_HOST", self.redis_host)
		port = int(os.getenv("REDIS_PORT", str(self.redis_port)))
		return redis.Redis(host=host, port=port, decode_responses=True)

	@staticmethod
	def _now_key_suffix() -> str:
		return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@register_tool("prompt-update")
class PromptUpdateTool(MemoryTraceableTool):
	"""Agent-callable tool for updating per-persona system prompts in Redis."""

	tool_name = "prompt-update"
	description = "Update system prompt for a persona and historize changes in Redis."
	parameters = [
		{
			"name": "persona",
			"type": "string",
			"description": "Target persona name (e.g., deployer, resiliency-optimizer, prompt-optimizer)",
			"required": True,
		},
		{
			"name": "system_prompt",
			"type": "string",
			"description": "Optional candidate prompt text. If omitted, reads from persona goal.yaml",
			"required": False,
		},
		{
			"name": "auto_authorized",
			"type": "boolean",
			"description": "Optional authorization flag for update workflows; currently accepted and treated as authorized",
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
			if not persona:
				result = {
					"success": False,
					"error": "Missing required parameter: persona",
					"exec_id": exec_id,
				}
				self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
				return json.dumps(result, ensure_ascii=False)

			updater = PromptUpdater()
			status = updater.update_system_prompt_with_status(
				persona=persona,
				system_prompt=args.get("system_prompt"),
			)
			status["exec_id"] = exec_id

			exec_status = ToolExecStatus.COMPLETED if status.get("success") else ToolExecStatus.FAILED
			self._post_call(exec_id, self.tool_name, args, exec_status, result=status)
			return json.dumps(status, ensure_ascii=False)
		except Exception as exc:
			result = {
				"success": False,
				"error": str(exc),
				"exec_id": exec_id,
			}
			if exec_id is not None:
				self._post_call(exec_id, self.tool_name, args, ToolExecStatus.FAILED, result=result)
			return json.dumps(result, ensure_ascii=False)