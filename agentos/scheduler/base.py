from abc import ABC, abstractmethod
from typing import Optional
import threading
from agentos.core.agent import Agent

class BaseScheduler(ABC):
    def __init__(self):
        self.lock = threading.Lock()

    @abstractmethod
    def submit(self, agent: Agent) -> None:
        """Add an agent to the scheduler queue."""
        pass

    @abstractmethod
    def get_next(self) -> Optional[Agent]:
        """Retrieve the next agent to execute based on the scheduling algorithm. 
        Returns None if queue is empty."""
        pass

    @abstractmethod
    def update(self, agent: Agent) -> None:
        """Called by the runtime when an agent finishes its slice/execution but isn't complete."""
        pass
