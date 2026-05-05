from __future__ import annotations

from pathlib import Path

import yaml


def write_persona_configs(base_dir: Path, persona: str, configs: dict[str, dict]) -> list[Path]:
    """Write persona yaml files under agent/personas/<persona>."""
    persona_dir = base_dir / "agent" / "personas" / persona
    persona_dir.mkdir(parents=True, exist_ok=True)

    file_map = {
        "agent": persona_dir / "agent.yaml",
        "goal": persona_dir / "goal.yaml",
        "sensors": persona_dir / "sensors.yaml",
        "actuators": persona_dir / "actuators.yaml",
    }

    written_files: list[Path] = []
    for config_name, file_path in file_map.items():
        payload = configs.get(config_name)
        if payload is None:
            continue
        with file_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=False)
        written_files.append(file_path)

    return written_files
