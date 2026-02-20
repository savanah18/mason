from dataclasses import dataclass, field
from typing import Union, List

from ..mixins.json import FromJsonMixin

@dataclass
class KafkaEventListenerConfig(FromJsonMixin):
    bootstrap_servers: List = field(default_factory=list)
    topics: List = field(default_factory=list)
    group_id: str = None
    auto_offset_reset: str = "latest"  # good for streaming, don't care about old
    session_timeout_ms: int = 30000  # timeout after 30 seconds
    request_timeout_ms: int = 40000  # request timeout
    connections_max_idle_ms: int = 540000