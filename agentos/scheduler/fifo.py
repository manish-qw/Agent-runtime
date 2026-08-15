from collections import deque
from typing import Optional
from agentos.core.agent import Agent
from agentos.scheduler.base import BaseScheduler

class FIFOScheduler(BaseScheduler):
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
        # For FIFO, an agent runs to completion. If it gets requeued, it goes to the back.
        self.submit(agent)
