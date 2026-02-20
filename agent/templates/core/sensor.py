from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

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
    def __init__(self, topics:List[str] = [], config: KafkaEventListenerConfig):
        self.topics = topics
        self.config = config

    def configure(self):
        self.consumer = KafkaConsumer( *self.topics, **self.config)

    def acquire_percepts(self):
        for message in self.consumer:
            raw_event = message.value
            percept = {
                "type": raw_event.get("event_type"),
                "source": "kafka",
                "data": raw_event,
                "timestamp": message.timestamp,
                "metadata": {
                    "topic": message.topic,
                    "partition": message.partition,
                    "offset": message.offset
                }
            }
            yield percept
            self.consumer.commit()