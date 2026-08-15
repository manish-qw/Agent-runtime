import pytest
from datetime import datetime
from agentos.core.agent import Agent
from agentos.core.state import AgentState
from agentos.core.task import Task

def test_agent_creation():
    """Test 1: Agent Creation (should start as CREATED)"""
    task = Task(id="t1", description="Test task", created_time=datetime.now())
    agent = Agent(agent_id="a1", task=task)
    
    assert agent.id == "a1"
    assert agent.state == AgentState.CREATED

def test_state_transition_allowed():
    """Test 2a: State Transition (Allowed)"""
    task = Task(id="t1", description="Test task", created_time=datetime.now())
    agent = Agent(agent_id="a1", task=task)
    
    # CREATED -> READY
    agent.transition_to(AgentState.READY)
    assert agent.state == AgentState.READY
    
    # READY -> RUNNING
    agent.transition_to(AgentState.RUNNING)
    assert agent.state == AgentState.RUNNING
    
    # RUNNING -> COMPLETED
    agent.transition_to(AgentState.COMPLETED)
    assert agent.state == AgentState.COMPLETED

def test_state_transition_invalid():
    """Test 2b: State Transition (Invalid)"""
    task = Task(id="t1", description="Test task", created_time=datetime.now())
    agent = Agent(agent_id="a1", task=task)
    
    # CREATED -> READY -> RUNNING -> COMPLETED
    agent.transition_to(AgentState.READY)
    agent.transition_to(AgentState.RUNNING)
    agent.transition_to(AgentState.COMPLETED)
    
    # Invalid: COMPLETED -> RUNNING
    with pytest.raises(ValueError):
        agent.transition_to(AgentState.RUNNING)

def test_multiple_agents():
    """Test 3: Multiple Agents have independent state"""
    task1 = Task(id="t1", description="Task 1", created_time=datetime.now())
    task2 = Task(id="t2", description="Task 2", created_time=datetime.now())
    task3 = Task(id="t3", description="Task 3", created_time=datetime.now())
    
    agent_a = Agent(agent_id="A", task=task1)
    agent_b = Agent(agent_id="B", task=task2)
    agent_c = Agent(agent_id="C", task=task3)
    
    # Transition only Agent A and B
    agent_a.transition_to(AgentState.READY)
    
    agent_b.transition_to(AgentState.READY)
    agent_b.transition_to(AgentState.RUNNING)
    
    assert agent_a.state == AgentState.READY
    assert agent_b.state == AgentState.RUNNING
    assert agent_c.state == AgentState.CREATED
