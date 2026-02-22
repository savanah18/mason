from typing import List, Any
import time

from .sensor import Sensor
from ..config.goals import Goal

class BaseAgent:
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

    def launch(self):
        while(not self.is_terminated):
            percepts =  [next(percept) for percept in self.perceive()] 
            self.reason(percepts)
            time.sleep(1)