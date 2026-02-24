from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Any, List, Dict
import json
import re

from kafka import KafkaConsumer

from ..config.kafka import KafkaEventListenerConfig

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
        print(config)
        topics = config.get("topics")
        config.pop('topics')
        # Add JSON deserializer for message values
        config['value_deserializer'] = lambda m: json.loads(m.decode('utf-8')) if m else None
        self.consumer = KafkaConsumer(**config)
        # regex based subscription
        pattern = "(" + "|".join(topics) + ")"
        self.consumer.subscribe(pattern = re.compile(pattern))

    def acquire_percepts(self):
        print("Acquiring percepts from Kafka...")
        for message in self.consumer:
            raw_event = message.value
            
            # Handle None or invalid messages
            if raw_event is None:
                print("Skipping None message")
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
            print("DEBUG percepts", percept)
            try:
                yield percept
            finally:
                self.consumer.commit()
            # Return after first message for single-shot acquisition
            return