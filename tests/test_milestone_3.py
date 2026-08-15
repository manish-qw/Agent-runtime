import pytest
import os
import concurrent.futures
from datetime import datetime
from agentos.core.agent import Agent
from agentos.core.task import Task
from agentos.core.state import AgentState
from agentos.scheduler.fifo import FIFOScheduler
from agentos.scheduler.priority import PriorityScheduler
from agentos.scheduler.round_robin import RoundRobinScheduler
from agentos.scheduler.token_aware import TokenAwareScheduler
from agentos.runtime.dummy_agents import MultiStepAgent

def create_dummy_agent(agent_id, priority=0):
    task = Task(id=f"t_{agent_id}", description="Dummy Task", created_time=datetime.now())
    return Agent(agent_id=agent_id, task=task, priority=priority)

def test_fifo_ordering():
    """Verify FIFO queue orders agents exactly as submitted."""
    scheduler = FIFOScheduler()
    agents = [create_dummy_agent(f"a{i}") for i in range(3)]
    
    for a in agents:
        scheduler.submit(a)
        
    for i in range(3):
        popped = scheduler.get_next()
        assert popped.id == f"a{i}"
        
    assert scheduler.get_next() is None

def test_priority_ordering():
    """Verify Priority queue orders by priority."""
    scheduler = PriorityScheduler()
    # Lower number = higher priority
    agent1 = create_dummy_agent("p10", priority=10)
    agent2 = create_dummy_agent("p1", priority=1)
    agent3 = create_dummy_agent("p5", priority=5)
    
    scheduler.submit(agent1)
    scheduler.submit(agent2)
    scheduler.submit(agent3)
    
    assert scheduler.get_next().id == "p1"
    assert scheduler.get_next().id == "p5"
    assert scheduler.get_next().id == "p10"

def test_round_robin_yielding():
    """Verify Round Robin properly resubmits yielding agents."""
    scheduler = RoundRobinScheduler()
    agent_a = create_dummy_agent("A")
    agent_b = create_dummy_agent("B")
    
    scheduler.submit(agent_a)
    scheduler.submit(agent_b)
    
    # A runs, yields
    run_a = scheduler.get_next()
    scheduler.update(run_a) # simulate yielding
    
    # B runs, finishes (no update call)
    run_b = scheduler.get_next()
    
    # A runs again
    run_a_again = scheduler.get_next()
    
    assert run_a.id == "A"
    assert run_b.id == "B"
    assert run_a_again.id == "A"

def test_token_aware_budgeting():
    """Verify the TokenAwareScheduler respects the token budget."""
    # Assuming each agent takes 100 tokens, budget of 150 allows 1 agent in flight.
    scheduler = TokenAwareScheduler(max_budget=150)
    a1 = create_dummy_agent("A", priority=1)
    a2 = create_dummy_agent("B", priority=1)
    
    scheduler.submit(a1)
    scheduler.submit(a2)
    
    # First agent should be dispatched
    dispatched_1 = scheduler.get_next()
    assert dispatched_1.id == "A"
    
    # Second agent should be deferred because budget is used
    dispatched_2 = scheduler.get_next()
    assert dispatched_2 is None
    
    # Complete agent 1 to free budget
    scheduler.complete_agent(dispatched_1)
    
    # Now agent 2 can run
    dispatched_3 = scheduler.get_next()
    assert dispatched_3.id == "B"

def test_concurrency_stress():
    """Submit 100 agents concurrently and ensure no data race drops them."""
    scheduler = FIFOScheduler()
    num_agents = 100
    
    def submit_agent(i):
        scheduler.submit(create_dummy_agent(f"agent_{i}"))
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(submit_agent, i) for i in range(num_agents)]
        concurrent.futures.wait(futures)
        
    # Drain queue and count
    drained = 0
    while scheduler.get_next() is not None:
        drained += 1
        
    assert drained == num_agents
