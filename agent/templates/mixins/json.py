import json
from dataclasses import dataclass, fields, asdict
from typing import Type, TypeVar, Any, Dict
from datetime import datetime

T = TypeVar("T")

class FromJsonMixin:
    @classmethod
    def from_json(cls: Type[T], data: str | Dict[str, Any]) -> T:
        """Generic JSON → dataclass initializer for any dataclass."""
        if isinstance(data, str):
            data = json.loads(data)

        # Collect valid field names
        valid_fields = {f.name: f for f in fields(cls)}

        # Filter JSON keys to only those that match dataclass fields
        filtered: Dict[str, Any] = {}
        for key, value in data.items():
            if key in valid_fields:
                f = valid_fields[key]
                # Handle datetime conversion
                if f.type is datetime and isinstance(value, str):
                    try:
                        value = datetime.fromisoformat(value)
                    except ValueError:
                        pass  # leave as string if not ISO format
                filtered[key] = value

        return cls(**filtered)
