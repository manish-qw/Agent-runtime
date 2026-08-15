import heapq
from typing import Optional
from agentos.core.agent import Agent
from agentos.scheduler.base import BaseScheduler

class TokenAwareScheduler(BaseScheduler):
    """
    A Priority-based scheduler that respects a token budget. 
    It defers execution of agents that would push the total estimated in-flight tokens 
    over the MAX_BUDGET.
    """
    def __init__(self, max_budget: int = 1000):
        super().__init__()
        self.heap = []
        self.deferred = []
        self.counter = 0
        self.max_budget = max_budget
        self.tokens_in_flight = 0

    def submit(self, agent: Agent) -> None:
        with self.lock:
            heapq.heappush(self.heap, (agent.priority, self.counter, agent))
            self.counter += 1

    def get_next(self) -> Optional[Agent]:
        with self.lock:
            # First, requeue any deferred agents to see if budget opened up
            while self.deferred:
                agent = self.deferred.pop(0)
                heapq.heappush(self.heap, (agent.priority, self.counter, agent))
                self.counter += 1

            deferred_this_round = []
            selected_agent = None

            while self.heap:
                _, _, agent = heapq.heappop(self.heap)
                
                # Assume a fixed cost for this step (e.g. 100 tokens per step)
                # In a real system, this would be an estimate stored on the agent.
                estimated_cost = 100 
                
                if self.tokens_in_flight + estimated_cost <= self.max_budget:
                    self.tokens_in_flight += estimated_cost
                    selected_agent = agent
                    break
                else:
                    deferred_this_round.append(agent)

            # Put deferred agents back into the deferred holding list
            self.deferred.extend(deferred_this_round)
            return selected_agent

    def update(self, agent: Agent) -> None:
        with self.lock:
            # The agent finished its step, free the budget
            estimated_cost = 100
            self.tokens_in_flight = max(0, self.tokens_in_flight - estimated_cost)
            # If it yielded, it needs to be resubmitted
            # In our implementation, we expect the runtime to call submit() if it yields, 
            # or we can do it here. We will just pass it to submit.
            self.submit(agent)

    def complete_agent(self, agent: Agent) -> None:
        """Called by runtime when an agent fully finishes or fails to free budget."""
        with self.lock:
            estimated_cost = 100
            self.tokens_in_flight = max(0, self.tokens_in_flight - estimated_cost)
