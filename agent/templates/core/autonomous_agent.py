from typing import List

from .sensor import Sensor
from ..models.goals import Goal

class BaseAgent:
    def __init__(self, 
        goal: Goal,  # can be added to system prompt
        sensors: List[Sensor],
        actuators: Any,
        *args,
        **kwargs
    ):
        self.goal = goal
        self.sensor = Sensor
        self.is_terminated = False
        # others
        self.verbose = kwargs.verbose or false

    def perceive(self):
        data = self.sensor.acquire_percepts()
    
    def plan(self):
        pass

    def act(self, tools):
        pass

    def terminate(self):
        self.terminate = True

    def run(self):
        while(not is_terminated):
            # TODO 
            pass

    