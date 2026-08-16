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

# Load .env file and override any system variables
load_dotenv(override=True)

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

def test_real_tool_calling_agent_crash_and_recovery(store):
    """
    End-to-End Integration Test:
    1. Spawn a tool_calling_agent_task with `simulate_crash=True`.
    2. Verify it crashes (FAILED state) after successfully making a Tool Call and checkpointing it.
    3. Run `bootstrap_recovery()` to rescue it (FAILED -> READY).
    4. Re-execute the agent to prove it resumes from the Checkpoint and successfully completes.
    """
    from agentos.runtime.real_agents import tool_calling_agent_task
    from agentos.tools.math_tools import add
    
    runtime = Runtime(store=store)
    agent_id = "tool_agent_crash_1"
    
    # 0. Setup
    task = Task(id=f"t_{agent_id}", description="Integration Test Tool Crash", created_time=datetime.now())
    agent = Agent(agent_id=agent_id, task=task)
    agent.transition_to(AgentState.READY)
    store.save_agent(agent)
    
    prompt = "What is 150 added to 250? You MUST use the add tool."
    tools = [add]
    
    # 1. First Execution (Programmed to Crash)
    runtime.execute(
        agent_id=agent_id,
        agent_callable=lambda: tool_calling_agent_task(store, agent_id, prompt, tools, simulate_crash=True),
        timeout=60
    )
    
    # 2. Verify Crash
    crashed_agent = store.load_agent(agent_id)
    assert crashed_agent.state == AgentState.FAILED
    
    checkpoint = store.load_checkpoint(agent_id)
    assert checkpoint is not None
    assert checkpoint.task_progress_marker == "crashed_once"
    # Verify the tool call was actually recorded in the checkpoint
    has_tool_call = False
    for msg in checkpoint.conversation_history:
        if isinstance(msg, dict) and "parts" in msg:
            for part in msg["parts"]:
                if "functionCall" in part or "function_call" in part:
                    has_tool_call = True
    assert has_tool_call, "The checkpoint did not record a tool call before crashing."
    
    # 3. OS Bootloader Recovery
    runtime.bootstrap_recovery()
    
    recovered_agent = store.load_agent(agent_id)
    assert recovered_agent.state == AgentState.READY
    
    # 4. Second Execution (Resume from Checkpoint)
    # We set simulate_crash=False so it finishes.
    result = runtime.execute(
        agent_id=agent_id,
        agent_callable=lambda: tool_calling_agent_task(store, agent_id, prompt, tools, simulate_crash=False),
        timeout=60
    )
    
    # 5. Verify Completion
    completed_agent = store.load_agent(agent_id)
    assert completed_agent.state == AgentState.COMPLETED
    assert result is not None
    assert "400" in result
    
    final_checkpoint = store.load_checkpoint(agent_id)
    assert final_checkpoint.task_progress_marker == "completed"
