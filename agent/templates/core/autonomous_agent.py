import time
import yaml
from typing import List, Any
import os

from .sensor import Sensor, KafkaEventListener
from .config.goals import GoalConfig, Goal
from .config.kafka import KafkaEventListenerConfig
from .config.goals import Goal

# Agent LIfecyle Management
from .alcm.agent_registry import AgentRegistry
registry = AgentRegistry()

PERSONA = os.getenv("PERSONA","deployer")

class AutonomousAgent:
    def __init__(self, 
        goal: Goal,
        sensors: List[Sensor],
        actuators: List[Any],
        *args,
        **kwargs
    ):
        self.goal = goal
        self.sensors = sensors
        self.actuators = actuators
        self.is_terminated = False
        # others
        self.verbose = kwargs.get('verbose') or False

        # context history
        self.messages = []

    def perceive(self) -> List[Any]:
        return [sensor.acquire_percepts() for sensor in self.sensors]

    def plan(self):
        pass

    def act(self, tools):
        pass

    def terminate(self):
        self.terminate = True

    def reason(self, percepts=[]):
        pass

    async def launch(self):
        while(not self.is_terminated):
            percepts =  [next(percept) for percept in self.perceive()] 
            try:
                registry.set_agent_status(PERSONA, "running")
                await self.reason(percepts)
                registry.set_agent_status(PERSONA, "waiting for tasks")
            except Exception as e:
                registry.set_agent_status(PERSONA, "exception occurred")
                print(f"Error during reasoning: {e}")

    def _initialize_sensors(self, config_path) -> List[Sensor]:
        with open(config_path, "r") as f: 
            data = yaml.safe_load(f)
            sensors = [
                globals()[sensor['type']](config=globals()[sensor['config_type']].from_json(sensor))
                for sensor in data['spec']
            ]
            return sensors

    def _initialize_goal(self, config_path) -> Goal:
        with open(config_path, "r") as f: 
            data = yaml.safe_load(f)
            goal = Goal(config=GoalConfig.from_json(data['spec']))
            return goal