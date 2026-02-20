from qwen_agent.agents import Assistant

from ..core.autonomous_agent import BaseAgent
from ..core.sensor import KafkaEventListener
from ..config.kafka import KafkaEventListenerConfig
from ..models.goals import Goal

class DeployerAgent(BaseAgent, Assistant):
    def __init__(self, sensor, goal):

