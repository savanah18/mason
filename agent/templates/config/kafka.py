from dataclasses import dataclass
from typing import Union, List

from ..mixins.json import FromJsonMixin

@dataclass
class KafkaEventListenerConfig(FromJsonMixin):
    bootstrap_servers: Union[str, List[str]]
    group_id: str = None
    auto_offset_reset : str = "latest" # good for streaming, dont care about old