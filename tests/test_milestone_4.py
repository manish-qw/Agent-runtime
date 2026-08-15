import pytest
from datetime import datetime
from agentos.core.agent import Agent, AgentState
from agentos.core.task import Task
from agentos.runtime.engine import Runtime
from agentos.llm.client import MockLLMClient
from agentos.runtime.real_agents import research_agent_task, coding_agent_task

def test_research_agent_with_mock(store):
    """Test that the research agent runs and records tokens."""
    runtime = Runtime(store=store)
    client = MockLLMClient(fixed_response="Mocked Summary", fixed_tokens=50)
    
    agent_id = "research_mock_1"
    task = Task(id="t_1", description="Research task", created_time=datetime.now())
    agent = Agent(agent_id=agent_id, task=task)
    agent.transition_to(AgentState.READY)
    store.save_agent(agent)

    # Execute
    result = runtime.execute(
        agent_id=agent_id, 
        agent_callable=lambda: research_agent_task(client, "Long document text..."),
        timeout=2
    )

    # Verify
    loaded = store.load_agent(agent_id)
    assert loaded.state == AgentState.COMPLETED
    assert result == "Mocked Summary"
    assert loaded.token_usage == 50
    assert "Used 50 tokens" in loaded.execution_history[-2]
    assert "Completed successfully: Mocked Summary" in loaded.execution_history[-1]

def test_coding_agent_with_mock(store):
    """Test that the coding agent runs and records tokens."""
    runtime = Runtime(store=store)
    client = MockLLMClient(fixed_response="print('Hello')", fixed_tokens=120)
    
    agent_id = "coding_mock_1"
    task = Task(id="t_2", description="Coding task", created_time=datetime.now())
    agent = Agent(agent_id=agent_id, task=task)
    agent.transition_to(AgentState.READY)
    store.save_agent(agent)

    # Execute
    result = runtime.execute(
        agent_id=agent_id, 
        agent_callable=lambda: coding_agent_task(client, "Write a hello world script."),
        timeout=2
    )

    # Verify
    loaded = store.load_agent(agent_id)
    assert loaded.state == AgentState.COMPLETED
    assert result == "print('Hello')"
    assert loaded.token_usage == 120
