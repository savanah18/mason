from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentRegistrationRequest(BaseModel):
    persona: str = Field(..., description="Persona name, used as logical agent id")
    agent: dict[str, Any] = Field(..., description="agent.yaml-equivalent JSON payload")
    goal: dict[str, Any] = Field(..., description="goal.yaml-equivalent JSON payload")
    sensors: dict[str, Any] = Field(..., description="sensors.yaml-equivalent JSON payload")
    actuators: dict[str, Any] = Field(..., description="actuators.yaml-equivalent JSON payload")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(extra="forbid")

    @field_validator("persona")
    @classmethod
    def validate_persona(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("persona must be non-empty")
        if not all(ch.isalnum() or ch in ("-", "_") for ch in normalized):
            raise ValueError("persona can only contain letters, digits, '-', '_' ")
        return normalized


class InstantiateAgentRequest(BaseModel):
    force_recreate: bool = Field(
        default=True,
        description="Remove existing <persona>-agent container before launching",
    )
    dry_run: bool = Field(
        default=False,
        description="Only print docker command without creating/updating container",
    )

    model_config = ConfigDict(extra="forbid")
