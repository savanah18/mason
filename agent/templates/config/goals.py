from dataclasses import dataclass, asdict
from typing import Union, List
import uuid
from enum import StrEnum
from datetime import datetime

from ..mixins.json import FromJsonMixin

class GoalStatus(StrEnum):
    PENDING     = "Pending"
    RUNNING     = "Running"
    COMPLETED   = "Completed"
    FAILED      = "Failed"
    CANCELLED   = "Cancelled"

@dataclass
class GoalConfig(FromJsonMixin):
    _id: str = uuid.uuid4()
    description: str = ""
    base_prompt: str = ""
    playbook: str = ""
    status: GoalStatus = GoalStatus.PENDING
    updated_at: datetime = datetime.now()
    completed_at: datetime = None
    max_iterations: int = 10
    timeout_seconds: int = 600
    dry_run: bool = False
    result: str = None
    error: str = None
    # others to follow

class Goal():
    def __init__(self, config: GoalConfig):
        for key, value in asdict(config).items(): 
            setattr(self, key, value)
    
    def start(self):
        self.status = GoalStatus.RUNNING

    def complete(self, result):
        self.status = GoalStatus.COMPLETED
        self.result = result
        now: datetime = datetime.now()
        self.completed_at = now
        self.updated_at = now

    def fail(self, error):
        self.status = GoalStatus.FAILED
        self.error = error
        now: datetime = datetime.now()
        self.completed_at = now
        self.updated_at = now

    def cancel(self):
        self.status = GoalStatus.CANCELLED
        now: datetime = datetime.now()
        self.completed_at = now
        self.updated_at = now

    def elapsed_second(self) -> int:
        return (datetime.now() - self.updated_at).seconds

    def is_timeout(self) -> bool:
        return self.elapsed_second > self.timeout_seconds

