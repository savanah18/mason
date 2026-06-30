"""Configuration resolution for persona-based agents."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import redis
import yaml

from .goals import Goal, GoalConfig

from .config import ConfigSource, PersonaConfig


class ConfigResolver:
    """Resolve agent configuration from Redis first, then YAML files."""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client or self._create_redis_client()

    def _create_redis_client(self) -> redis.Redis:
        host = os.getenv("REDIS_HOST", "redis")
        port = int(os.getenv("REDIS_PORT", "6379"))
        return redis.Redis(host=host, port=port, decode_responses=True)

    def _latest_key(self, section: str, persona: str) -> str:
        return f"agent-records:{section}:{persona}:latest"

    def _load_from_redis(self, section: str, persona: str) -> Tuple[Optional[Dict[str, Any]], Optional[ConfigSource]]:
        key = self._latest_key(section, persona)
        try:
            record = self.redis_client.hgetall(key) or {}
        except Exception:
            return None, None

        payload = record.get("payload")
        if not payload:
            return None, None

        try:
            parsed = json.loads(payload)
        except Exception:
            return None, None

        source = ConfigSource(
            section=section,
            source="redis",
            key=key,
            timestamp=record.get("updated_at") or record.get("timestamp"),
        )
        return parsed, source

    def _load_from_file(self, path: Path, section: str) -> Tuple[Optional[Dict[str, Any]], Optional[ConfigSource]]:
        if not path.exists():
            return None, None

        with path.open("r", encoding="utf-8") as handle:
            parsed = yaml.safe_load(handle)

        source = ConfigSource(section=section, source="file", key=str(path))
        return parsed, source

    @staticmethod
    def _extract_spec(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        spec = payload.get("spec")
        return spec if isinstance(spec, dict) else payload

    @staticmethod
    def _extract_spec_list(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {"spec": []}
        spec = payload.get("spec")
        if isinstance(spec, list):
            return {"spec": spec}
        return payload

    def _resolve_goal(self, persona: str, base_path: Path) -> Tuple[Goal, ConfigSource]:
        redis_payload, redis_source = self._load_from_redis("goal", persona)
        if redis_payload:
            goal_data = self._extract_spec(redis_payload)
            return Goal(config=GoalConfig.from_json(goal_data)), redis_source

        file_payload, file_source = self._load_from_file(base_path / "personas" / persona / "goal.yaml", "goal")
        if file_payload:
            goal_data = self._extract_spec(file_payload)
            return Goal(config=GoalConfig.from_json(goal_data)), file_source

        raise FileNotFoundError(f"Unable to resolve goal config for persona={persona}")

    def _resolve_sensors(self, persona: str, base_path: Path) -> Tuple[Dict[str, Any], ConfigSource]:
        redis_payload, redis_source = self._load_from_redis("sensors", persona)
        if redis_payload:
            return self._extract_spec_list(redis_payload), redis_source

        file_payload, file_source = self._load_from_file(base_path / "personas" / persona / "sensors.yaml", "sensors")
        if file_payload:
            return self._extract_spec_list(file_payload), file_source

        raise FileNotFoundError(f"Unable to resolve sensors config for persona={persona}")

    def _resolve_actuators(self, persona: str, base_path: Path) -> Tuple[Dict[str, Any], ConfigSource]:
        redis_payload, redis_source = self._load_from_redis("actuators", persona)
        if redis_payload:
            return self._extract_spec(redis_payload), redis_source

        file_payload, file_source = self._load_from_file(base_path / "personas" / persona / "actuators.yaml", "actuators")
        if file_payload:
            return self._extract_spec(file_payload), file_source

        raise FileNotFoundError(f"Unable to resolve actuators config for persona={persona}")

    def _resolve_llm_cfg(self, persona: str, base_path: Path) -> Tuple[Dict[str, Any], ConfigSource]:
        redis_payload, redis_source = self._load_from_redis("llm_cfg", persona)
        if redis_payload:
            return self._extract_spec(redis_payload), redis_source

        inference_server_type = os.getenv("INFERENCE_SERVER_TYPE", "tensorrt-llm")
        candidate_paths = [
            base_path / "templates" / "llm" / f"qwen.{inference_server_type}.yaml",
            base_path / "templates" / "llm" / "qwen.yaml",
        ]
        for candidate in candidate_paths:
            file_payload, file_source = self._load_from_file(candidate, "llm_cfg")
            if file_payload:
                return self._extract_spec(file_payload), file_source

        default_cfg = {
            "model": "Qwen3-4B-Instruct",
            "model_server": os.getenv("LLM_SERVER", "http://localhost:8001/v1"),
            "generate_cfg": {
                "temperature": 0.1 if os.getenv("AGENT_MODE", "dev") == "eval" else 0.8,
                "top_p": 0.9,
                "repetition_penalty": 1.1,
            },
        }
        return default_cfg, ConfigSource(section="llm_cfg", source="default")

    def resolve(self, persona: str, base_path: str | Path) -> PersonaConfig:
        base_path = Path(base_path)

        goal, goal_source = self._resolve_goal(persona, base_path)
        sensors, sensors_source = self._resolve_sensors(persona, base_path)
        actuators, actuators_source = self._resolve_actuators(persona, base_path)
        llm_cfg, llm_cfg_source = self._resolve_llm_cfg(persona, base_path)

        return PersonaConfig(
            persona=persona,
            goal=goal,
            sensors=sensors,
            actuators=actuators,
            llm_cfg=llm_cfg,
            goal_source=goal_source,
            sensors_source=sensors_source,
            actuators_source=actuators_source,
            llm_cfg_source=llm_cfg_source,
        )