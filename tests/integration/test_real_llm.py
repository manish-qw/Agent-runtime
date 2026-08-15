import pytest
import os
from datetime import datetime
from dotenv import load_dotenv
from agentos.core.agent import Agent, AgentState
from agentos.core.task import Task
from agentos.runtime.engine import Runtime
from agentos.llm.client import GeminiLLMClient
from agentos.runtime.real_agents import coding_agent_task
from agentos.runtime.real_agents import research_agent_task

# Load .env file
load_dotenv()

# Skip these tests if no API key is set
pytestmark = pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY environment variable not set"
)

def test_real_gemini_coding_agent(store):
    """Test actual execution of a single Gemini 2.5 Flash Lite coding agent."""
    runtime = Runtime(store=store)
    client = GeminiLLMClient() 
    
    agent_id = "coding_real_1"
    task = Task(id="t_real_1", description="Write a hello world in Python", created_time=datetime.now())
    agent = Agent(agent_id=agent_id, task=task)
    agent.transition_to(AgentState.READY)
    store.save_agent(agent)

    result = runtime.execute(
        agent_id=agent_id, 
        agent_callable=lambda: coding_agent_task(client, "Write a simple hello world in Python. Output only the code."),
        timeout=30
    )

    loaded = store.load_agent(agent_id)
    assert loaded.state == AgentState.COMPLETED
    assert "print" in result.lower()
    assert loaded.token_usage > 0

def test_real_gemini_multiple_agents_concurrently(store):
    """
    Test submitting 5 real agents (3 Research, 2 Coding) concurrently.
    This proves the Runtime ThreadPool and Token tracking work under real API load.
    """
    runtime = Runtime(store=store, max_workers=5)
    client = GeminiLLMClient()
    
    import concurrent.futures

    # Setup 5 dummy tasks
    tasks = [
        ("research_1", lambda: research_agent_task(client, "AgentOS is an operating system for LLM agents. It has a scheduler, a database, and an execution engine.")),
        ("research_2", lambda: research_agent_task(client, "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability.")),
        ("research_3", lambda: research_agent_task(client, "Artificial intelligence is the intelligence of machines or software, as opposed to the intelligence of humans or animals.")),
        ("coding_1", lambda: coding_agent_task(client, "Write a function to add two numbers in Python.")),
        ("coding_2", lambda: coding_agent_task(client, "Write a function to multiply two numbers in Python."))
    ]

    # Initialize all agents in the DB
    for agent_id, _ in tasks:
        task = Task(id=f"t_{agent_id}", description="Integration Test Task", created_time=datetime.now())
        agent = Agent(agent_id=agent_id, task=task)
        agent.transition_to(AgentState.READY)
        store.save_agent(agent)

    # Execute them concurrently using a local thread pool
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_id = {
            executor.submit(runtime.execute, agent_id, callable, 30): agent_id
            for agent_id, callable in tasks
        }
        
        for future in concurrent.futures.as_completed(future_to_id):
            agent_id = future_to_id[future]
            try:
                results[agent_id] = future.result()
            except Exception as exc:
                results[agent_id] = None

    # Verify all 5 agents succeeded and recorded token usage
    for agent_id, _ in tasks:
        loaded = store.load_agent(agent_id)
        assert loaded.state == AgentState.COMPLETED
        assert loaded.token_usage > 0
        assert results[agent_id] is not None
