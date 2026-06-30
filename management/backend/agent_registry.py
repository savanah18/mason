from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import redis


class AgentRegistry:
    ONE_MONTH_TTL_SECONDS = 30 * 24 * 60 * 60
    RECORD_SECTIONS = ("agent", "goal", "sensors", "actuators")

    def __init__(self, redis_host: str = "redis", redis_port: int = 6379):
        self.client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)

    @staticmethod
    def _ts() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _from_json(value: str | None, default: Any) -> Any:
        if value is None:
            return default
        try:
            return json.loads(value)
        except Exception:
            return default

    def register_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        persona = payload["persona"]
        registry_metadata = payload.get("metadata", {})

        section_results: dict[str, dict[str, Any]] = {}
        for section_name in self.RECORD_SECTIONS:
            section_payload = payload.get(section_name, {})
            section_results[section_name] = self._upsert_section_record(
                persona,
                section_name,
                section_payload,
                registry_metadata,
            )

        prompt_status = self._upsert_prompt_record(persona, payload.get("goal", {}), registry_metadata)
        # mark agent as registered in the latest agent section
        try:
            self.set_agent_status(persona, "registered")
        except Exception:
            pass

        return {
            "persona": persona,
            "sections": section_results,
            "prompt": prompt_status,
        }

    def set_agent_status(self, persona: str, status: str) -> dict[str, Any]:
        """Set a simple status field on the agent latest record.

        Writes `status` and `status_updated_at` to `agent-records:agent:<persona>:latest`.
        Returns the result mapping written.
        """
        latest_key = f"{self._section_key_prefix('agent')}:{persona}:latest"
        timestamp = self._ts()
        mapping = {
            "status": status,
            "status_updated_at": timestamp,
        }

        # ensure the latest key exists; if not, create a minimal holder so status is preserved
        existing = self.client.hgetall(latest_key) or {}
        if not existing:
            # create a minimal agent record so status has a place
            base_mapping = {
                "schema": "agent",
                "persona": persona,
                "payload": self._json({}),
                "registry_metadata": self._json({}),
                "metadata": self._json({"persona": persona, "created_at": timestamp}),
                "created_at": timestamp,
            }
            self.client.hset(latest_key, mapping=base_mapping)

        # set status fields
        self.client.hset(latest_key, mapping=mapping)

        return {"success": True, "persona": persona, "latest_key": latest_key, "status": status, "status_updated_at": timestamp}

    def _section_key_prefix(self, section_name: str) -> str:
        return f"agent-records:{section_name}"

    def _upsert_section_record(
        self,
        persona: str,
        section_name: str,
        section_payload: Any,
        registry_metadata: Any,
    ) -> dict[str, Any]:
        timestamp = self._ts()
        latest_key = f"{self._section_key_prefix(section_name)}:{persona}:latest"
        historized_key = f"{self._section_key_prefix(section_name)}:{persona}:{timestamp}"

        payload_json = self._json(section_payload)
        existing = self.client.hgetall(latest_key) or {}

        mapping = {
            "schema": section_name,
            "persona": persona,
            "payload": payload_json,
            "registry_metadata": self._json(registry_metadata or {}),
            "metadata": self._json({"persona": persona, "section": section_name, "created_at": historized_key}),
            "created_at": timestamp,
        }

        changed = existing.get("payload") != payload_json or existing.get("metadata") != mapping["metadata"]
        changed = changed or existing.get("registry_metadata") != mapping["registry_metadata"]

        if not existing:
            action = "created"
        elif changed:
            action = "updated"
        else:
            action = "no-change"

        if action != "no-change":
            self.client.hset(latest_key, mapping=mapping)
            self.client.hset(historized_key, mapping=mapping)
            self.client.expire(historized_key, self.ONE_MONTH_TTL_SECONDS)

        return {
            "success": True,
            "action": action,
            "latest_key": latest_key,
            "historized_key": historized_key if action != "no-change" else existing.get("created_at"),
            "schema": section_name,
        }

    def _upsert_prompt_record(self, persona: str, goal: dict[str, Any], registry_metadata: Any) -> dict[str, Any]:
        spec = goal.get("spec", {}) if isinstance(goal, dict) else {}

        prompt = (spec.get("description") or goal.get("system") or "").strip()
        remarks = spec.get("remarks", {}) or goal.get("remarks", {}) or {}
        feedback = spec.get("feedback", "") or goal.get("feedback", "")

        if not prompt:
            return {
                "success": False,
                "updated": False,
                "reason": "empty-prompt",
                "persona": persona,
                "latest_key": None,
            }

        latest_key = f"system-prompts:{persona}:latest"
        historized_key = f"system-prompts:{persona}:{self._ts()}"
        existing = self.client.hgetall(latest_key) or {}

        mapping = {
            "schema": "system-prompt",
            "persona": persona,
            "prompt": prompt,
            "goal": self._json(goal),
            "registry_metadata": self._json(registry_metadata or {}),
            "remarks": self._json(remarks),
            "feedback": self._json(feedback),
            "metadata": self._json({"persona": persona, "created_at": historized_key}),
            "created_at": historized_key,
        }

        if not existing.get("prompt"):
            self.client.hset(latest_key, mapping=mapping)
            self.client.hset(historized_key, mapping=mapping)
            self.client.expire(historized_key, self.ONE_MONTH_TTL_SECONDS)
            return {
                "success": True,
                "updated": True,
                "reason": "created",
                "persona": persona,
                "latest_key": historized_key,
            }

        if existing.get("prompt") != prompt:
            self.client.hset(latest_key, mapping=mapping)
            self.client.hset(historized_key, mapping=mapping)
            self.client.expire(historized_key, self.ONE_MONTH_TTL_SECONDS)
            return {
                "success": True,
                "updated": True,
                "reason": "updated",
                "persona": persona,
                "latest_key": historized_key,
            }

        metadata = self._from_json(existing.get("metadata"), {})
        return {
            "success": True,
            "updated": False,
            "reason": "no-change",
            "persona": persona,
            "latest_key": metadata.get("created_at"),
        }

    def _load_section_latest(self, persona: str, section_name: str) -> dict[str, Any] | None:
        latest_key = f"{self._section_key_prefix(section_name)}:{persona}:latest"
        data = self.client.hgetall(latest_key) or {}
        if not data:
            return None

        return {
            "schema": data.get("schema", section_name),
            "persona": persona,
            "payload": self._from_json(data.get("payload"), {}),
            "created_at": data.get("created_at"),
            "metadata": self._from_json(data.get("metadata"), {}),
        }

    def load_latest_agent_config(self, persona: str) -> dict[str, Any] | None:
        agent_record = self._load_section_latest(persona, "agent")
        goal_record = self._load_section_latest(persona, "goal")
        sensors_record = self._load_section_latest(persona, "sensors")
        actuators_record = self._load_section_latest(persona, "actuators")

        if not any((agent_record, goal_record, sensors_record, actuators_record)):
            return None

        return {
            "persona": persona,
            "agent": (agent_record or {}).get("payload", {}),
            "goal": (goal_record or {}).get("payload", {}),
            "sensors": (sensors_record or {}).get("payload", {}),
            "actuators": (actuators_record or {}).get("payload", {}),
            "metadata": (agent_record or goal_record or sensors_record or actuators_record or {}).get("registry_metadata", {}),
            "created_at": (agent_record or goal_record or sensors_record or actuators_record or {}).get("created_at"),
            "records": {
                "agent": agent_record,
                "goal": goal_record,
                "sensors": sensors_record,
                "actuators": actuators_record,
            },
        }

    def delete_agent(self, persona: str) -> dict[str, Any]:
        deleted_keys: list[str] = []

        for section_name in self.RECORD_SECTIONS:
            latest_key = f"{self._section_key_prefix(section_name)}:{persona}:latest"
            history_pattern = f"{self._section_key_prefix(section_name)}:{persona}:*"

            history_keys = [key for key in self.client.scan_iter(match=history_pattern) if key != latest_key]

            if self.client.delete(latest_key):
                deleted_keys.append(latest_key)
            if history_keys:
                self.client.delete(*history_keys)
                deleted_keys.extend(history_keys)

        prompt_latest_key = f"system-prompts:{persona}:latest"
        prompt_history_pattern = f"system-prompts:{persona}:*"
        prompt_history_keys = [key for key in self.client.scan_iter(match=prompt_history_pattern) if key != prompt_latest_key]

        if self.client.delete(prompt_latest_key):
            deleted_keys.append(prompt_latest_key)
        if prompt_history_keys:
            self.client.delete(*prompt_history_keys)
            deleted_keys.extend(prompt_history_keys)

        return {
            "success": True,
            "persona": persona,
            "deleted_count": len(deleted_keys),
            "deleted_keys": sorted(deleted_keys),
        }
