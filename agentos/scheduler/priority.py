import heapq
from typing import Optional
from agentos.core.agent import Agent
from agentos.scheduler.base import BaseScheduler

class PriorityScheduler(BaseScheduler):
    def __init__(self):
        super().__init__()
        self.heap = []
        self.counter = 0  # Tie-breaker for agents with same priority (maintains FIFO for same priority)

    def submit(self, agent: Agent) -> None:
        with self.lock:
            # Lower number = higher priority. 
            # heapq is a min-heap, so smaller priority values pop first.
            heapq.heappush(self.heap, (agent.priority, self.counter, agent))
            self.counter += 1

    def get_next(self) -> Optional[Agent]:
        with self.lock:
            if not self.heap:
                return None
            _, _, agent = heapq.heappop(self.heap)
            return agent

    def update(self, agent: Agent) -> None:
        self.submit(agent)
