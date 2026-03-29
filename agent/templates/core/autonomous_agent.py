import time
import yaml
from typing import List, Any

from .sensor import Sensor, KafkaEventListener
from templates.config.goals import GoalConfig, Goal
from templates.config.kafka import KafkaEventListenerConfig
from ..config.goals import Goal

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
            await self.reason(percepts)

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