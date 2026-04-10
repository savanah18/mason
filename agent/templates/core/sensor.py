from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any, List, Dict
import json
import re

from kafka import KafkaConsumer

from ..config.kafka import KafkaEventListenerConfig

def safe_deserializer(m):
    if not m:
        return None
    try:
        return json.loads(m.decode("utf-8"))
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
                print("Skipping empty message")
                continue
                
            percept = {
                "type": raw_event.get("event_type", raw_event.get("event")),
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