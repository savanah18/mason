"""Resolved configuration objects for persona-based agents."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from .goals import Goal


@dataclass
class ConfigSource:
    """Metadata about where config was loaded from."""
    section: str
    source: str
    key: Optional[str] = None
    timestamp: Optional[str] = None


@dataclass
class PersonaConfig:
    persona: str
    goal: Goal
    sensors: Dict[str, Any]
    actuators: Dict[str, Any]
    llm_cfg: Dict[str, Any]

    goal_source: ConfigSource
    sensors_source: ConfigSource
    actuators_source: ConfigSource
    llm_cfg_source: ConfigSource

    resolved_at: Optional[str] = None
    
    def __post_init__(self):
        if self.resolved_at is None:
            self.resolved_at = datetime.utcnow().isoformat()
