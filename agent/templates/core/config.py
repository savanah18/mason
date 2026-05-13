"""PersonaConfig: resolved configuration for an agent persona.

Holds all resolved configuration (goal, sensors, actuators, llm_cfg) with provenance metadata.
This is the output of ConfigResolver and input to agent constructors.
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from datetime import datetime


@dataclass
class ConfigSource:
    """Metadata about where config was loaded from."""
    section: str  # 'goal', 'sensors', 'actuators', 'llm_cfg'
    source: str  # 'redis', 'file', 'env'
    key: Optional[str] = None  # redis key or file path
    timestamp: Optional[str] = None  # ISO timestamp if from redis


@dataclass
class PersonaConfig:
    """Resolved configuration for a persona agent.
    
    All sections are loaded with DB-first/file-fallback precedence.
    Each section has provenance metadata.
    """
    persona: str
    goal: Dict[str, Any]  # resolved goal config
    sensors: Dict[str, Any]  # resolved sensors config
    actuators: Dict[str, Any]  # resolved actuators config
    llm_cfg: Dict[str, Any]  # resolved llm config
    
    # Provenance tracking
    goal_source: ConfigSource
    sensors_source: ConfigSource
    actuators_source: ConfigSource
    llm_cfg_source: ConfigSource
    
    resolved_at: str = None  # ISO timestamp
    
    def __post_init__(self):
        if self.resolved_at is None:
            self.resolved_at = datetime.utcnow().isoformat()
