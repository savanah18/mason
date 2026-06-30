from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any, List, Dict
import json
import re

from kafka import KafkaConsumer

from .config.kafka import KafkaEventListenerConfig

def safe_deserializer(m):
    if not m:
        return None
    try:
        parsed = json.loads(m.decode("utf-8"))
        if not isinstance(parsed, dict):
            print("Skipping non-object JSON:", parsed)
            return None
        return parsed
    except json.JSONDecodeError:
        print("Skipping invalid JSON:", m)
        return None

class Sensor(ABC):
    @abstractmethod
    def acquire_percepts(self)->Any: 
        pass

    @abstractmethod
    def configure(self)->Any:
        pass


class KafkaEventListener(Sensor):
    def __init__(self, config: KafkaEventListenerConfig = {}):
        config = asdict(config)
        self.configure(config)

    def configure(self, config: Dict):
        topics = config.get("topics")
        config.pop('topics')
        # Add JSON deserializer for message values
        config['value_deserializer'] = safe_deserializer
        self.consumer = KafkaConsumer(**config)
        # regex based subscription
        pattern = "(" + "|".join(topics) + ")"
        print(f"Listenting from {pattern}")
        self.consumer.subscribe(pattern = re.compile(pattern))

    def acquire_percepts(self):
        print("Acquiring percepts from Kafka...")
        for message in self.consumer:
            raw_event = message.value
            
            # Handle None or invalid messages
            if not raw_event:
                print("Skipping empty or invalid message")
                continue
                
            percept = {
                "source": "kafka",
                "data": raw_event,
                "timestamp": message.timestamp,
                "metadata": {
                    "topic": message.topic,
                    "partition": message.partition,
                    "offset": message.offset
                }
            }
            print("Perceived\n", percept)
            try:
                yield percept
            finally:
                self.consumer.commit()
            # Return after first message for single-shot acquisition
            return


def build_sensors_from_config(sensor_config: Any) -> List[Sensor]:
    """Build live Sensor instances from resolved sensor config."""
    sensors: List[Sensor] = []
    sensor_defs = sensor_config.get("spec", []) if isinstance(sensor_config, dict) else sensor_config

    sensor_registry = {
        "KafkaEventListener": KafkaEventListener,
    }
    config_registry = {
        "KafkaEventListenerConfig": KafkaEventListenerConfig,
    }

    for sensor in sensor_defs or []:
        sensor_cls = sensor_registry.get(sensor.get("type"))
        config_cls = config_registry.get(sensor.get("config_type"))
        if sensor_cls is None or config_cls is None:
            raise ValueError(f"Unsupported sensor definition: {sensor}")
        sensors.append(sensor_cls(config=config_cls.from_json(sensor)))

    return sensors