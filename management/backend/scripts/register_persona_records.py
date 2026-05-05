#!/usr/bin/env python3
from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "management"))

from backend.agent_registry import AgentRegistry

DEFAULT_PERSONAS = ("deployer", "resiliency-optimizer", "prompt-optimizer")


def load_yaml_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}, got {type(data)}")
    return data


def load_optional_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return load_yaml_file(path)


def build_payload(persona: str) -> dict[str, Any]:
    persona_dir = PROJECT_ROOT / "agent" / "personas" / persona
    return {
        "persona": persona,
        "agent": load_optional_yaml_file(persona_dir / "agent.yaml"),
        "goal": load_yaml_file(persona_dir / "goal.yaml"),
        "sensors": load_yaml_file(persona_dir / "sensors.yaml"),
        "actuators": load_yaml_file(persona_dir / "actuators.yaml"),
        "metadata": {
            "source": "agent/personas",
            "persona": persona,
            "registered_by": "register_persona_records.py",
        },
    }


def main(argv: list[str]) -> int:
    personas = argv[1:] or list(DEFAULT_PERSONAS)
    registry = AgentRegistry(redis_host=os.environ.get("REDIS_HOST", "redis"), redis_port=int(os.environ.get("REDIS_PORT", "6379")))

    for persona in personas:
        payload = build_payload(persona)
        result = registry.register_agent(payload)
        print(f"registered {persona}: {result}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
