from collections import deque
from typing import Optional
from agentos.core.agent import Agent
from agentos.scheduler.base import BaseScheduler

class RoundRobinScheduler(BaseScheduler):
    def __init__(self):
        super().__init__()
        self.queue = deque()

    def submit(self, agent: Agent) -> None:
        with self.lock:
            self.queue.append(agent)

    def get_next(self) -> Optional[Agent]:
        with self.lock:
            if not self.queue:
                return None
            return self.queue.popleft()

    def update(self, agent: Agent) -> None:
        """
        In Cooperative Round Robin, if an agent 'yields' (i.e. is not COMPLETED), 
        we put it back at the end of the queue.
        """
        self.submit(agent)
