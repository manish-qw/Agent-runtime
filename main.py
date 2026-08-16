import time
import os
from datetime import datetime
from dotenv import load_dotenv

from agentos.core.agent import Agent, AgentState
from agentos.core.task import Task
from agentos.storage.sqlite_store import SQLiteStore
from agentos.runtime.engine import Runtime
from agentos.llm.client import GeminiLLMClient
from agentos.runtime.real_agents import coding_agent_task
from agentos.runtime.real_agents import research_agent_task

from agentos.runtime.real_agents import tool_calling_agent_task
from agentos.scheduler.token_aware import TokenAwareScheduler

from agentos.tools.math_tools import add, multiply
from agentos.tools.fs_tools import list_files, read_file, write_file
from agentos.tools.web_tools import search_web
from agentos.tools.weather_tools import get_weather

def main():
    # 1. Setup the OS Environment
    print("Booting AgentOS...")
    # Load environment variables (API keys)
    load_dotenv(override=True)
    
    # We will use a permanent database so you can inspect it anytime!
    db_path = "agentos.db"
    store = SQLiteStore(db_path=db_path)
    
    # Initialize the Scheduler and Runtime engine
    scheduler = TokenAwareScheduler(max_budget=50)
    runtime = Runtime(store=store, scheduler=scheduler)
    client = GeminiLLMClient()
    # 2. Setup 3 True Tool-Calling Agents
    tasks = [
        (
            "math_agent", 
            "If John has 5 apples, buys 3 more, then multiplies his stash by 4, how many does he have? You MUST use the add and multiply tools.",
            [add, multiply]
        ),
        (
            "fs_agent",
            "List the files in the current directory ('.'). Find the file named 'dummy_log.txt', read it, summarize the error you find, and write that summary into a new file called 'report.txt'.",
            [list_files, read_file, write_file]
        ),
        (
            "world_agent",
            "What is the current weather in Tokyo? After finding out, search the web for 'things to do in Tokyo when it is [insert weather condition here]'.",
            [get_weather, search_web]
        )
    ]

    # Create dummy file for fs_agent
    with open("dummy_log.txt", "w") as f:
        f.write("System OK. Error: Network timeout on port 8080. System OK.")

    agent_ids = []
    for i, (role, prompt, tools) in enumerate(tasks):
        agent_id = f"{role}_{int(time.time())}"
        agent_ids.append(agent_id)
        task = Task(id=f"t_{agent_id}", description="True Tool-Calling loop", created_time=datetime.now())
        agent = Agent(agent_id=agent_id, task=task, priority=10 - i)
        agent.transition_to(AgentState.READY)
        store.save_agent(agent)
        print(f"Created Agent [{agent_id}]")

    # 3. Phase 1: Execute and observe the CRASH
    print(f"\n--- PHASE 1: Initial Execution (Expecting Crashes) ---")
    print("Executing agents sequentially to respect Gemini API rate limits...")
    for (role, prompt, tools), agent_id in zip(tasks, agent_ids):
        print(f"Running {agent_id}...")
        runtime.execute(
            agent_id=agent_id,
            agent_callable=lambda p=prompt, aid=agent_id, t=tools: tool_calling_agent_task(store, aid, p, t, simulate_crash=True),
            timeout=60
        )
        crashed_agent = store.load_agent(agent_id)
        print(f" -> Resulting State: {crashed_agent.state.name}")
        
    print(f"\n--- PHASE 2: System Recovery ---")
    print("Re-transitioning crashed agents back to READY and resuming them...")
    runtime.bootstrap_recovery()
        
    print(f"\n--- PHASE 3: Resuming from Checkpoints ---")
    for (role, prompt, tools), agent_id in zip(tasks, agent_ids):
        print(f"Resuming {agent_id}...")
        runtime.execute(
            agent_id=agent_id,
            agent_callable=lambda p=prompt, aid=agent_id, t=tools: tool_calling_agent_task(store, aid, p, t),
            timeout=60
        )
    
    # 4. View the Results
    print("\n" + "="*50)
    print("AGENT EXECUTION COMPLETE")
    print("="*50)
    
    for agent_id in agent_ids:
        final_agent = store.load_agent(agent_id)
        print(f"\n--- {agent_id.upper()} ---")
        print(f"State: {final_agent.state.name} | Tokens Used: {final_agent.token_usage}")
        print(f"Execution History: {final_agent.execution_history}")
    
    print("\n" + "="*50)
    print(f"You can now open '{db_path}' in VS Code using the SQLite Viewer extension to see the tool calls saved permanently!")

if __name__ == "__main__":
    main()
