import pytest
import os
from datetime import datetime
from agentos.core.agent import Agent
from agentos.core.task import Task
from agentos.core.state import AgentState
from agentos.storage.sqlite_store import SQLiteStore
from agentos.runtime.engine import Runtime
from agentos.runtime.dummy_agents import sleep_agent, exception_agent, sleep_forever_agent



def test_successful_execution(store):
    """Run multiple dummy agents to completion."""
    runtime = Runtime(store=store)
    
    agent_ids = []
    # 1. Create 10 agents
    for i in range(10):
        agent_id = f"success_agent_{i}"
        task = Task(id=f"t_{i}", description="Sleep task", created_time=datetime.now())
        agent = Agent(agent_id=agent_id, task=task)
        agent.transition_to(AgentState.READY)
        store.save_agent(agent)
        agent_ids.append(agent_id)

    # 2. Execute all 10 agents
    for agent_id in agent_ids:
        result = runtime.execute(agent_id, lambda: sleep_agent(0.1), timeout=2.0)
        assert result == "Slept for 0.1 seconds."
        
        loaded_agent = store.load_agent(agent_id)
        assert loaded_agent.state == AgentState.COMPLETED
        assert "Completed successfully" in loaded_agent.execution_history[-1]

def test_exception_isolation(store):
    """Run an exception-raising agent and ensure it fails gracefully."""
    runtime = Runtime(store=store)
    
    agent_id = "crash_agent"
    task = Task(id="t_crash", description="Crash task", created_time=datetime.now())
    agent = Agent(agent_id=agent_id, task=task)
    agent.transition_to(AgentState.READY)
    store.save_agent(agent)
    
    # Execute agent
    runtime.execute(agent_id=agent_id, agent_callable=exception_agent, timeout=2)
    
    # Verify it failed and didn't crash the test runner
    loaded = store.load_agent(agent_id)
    assert loaded.state == AgentState.FAILED
    assert "Exception raised - Intentional agent crash." in loaded.execution_history[-1]

def test_timeout_handling(store):
    """Run an infinite loop agent and ensure it times out gracefully."""
    runtime = Runtime(store=store)
    
    agent_id = "hung_agent"
    task = Task(id="t_hung", description="Hung task", created_time=datetime.now())
    agent = Agent(agent_id=agent_id, task=task)
    agent.transition_to(AgentState.READY)
    store.save_agent(agent)
    
    # Execute agent with a strict 1-second timeout
    runtime.execute(agent_id=agent_id, agent_callable=sleep_forever_agent, timeout=1)
    
    # Verify it was aborted and marked as FAILED
    loaded = store.load_agent(agent_id)
    assert loaded.state == AgentState.FAILED
    assert "timed out after 1s" in loaded.execution_history[-1]
