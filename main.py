import time
import os
from datetime import datetime
from dotenv import load_dotenv

from agentos.core.agent import Agent, AgentState
from agentos.core.task import Task
from agentos.storage.sqlite_store import SQLiteStore
from agentos.runtime.engine import Runtime
from agentos.runtime.real_agents import tool_calling_agent_task
from agentos.scheduler.token_aware import TokenAwareScheduler

from agentos.tools.math_tools import add, multiply
from agentos.tools.fs_tools import list_files, read_file, write_file
from agentos.tools.web_tools import search_web
from agentos.tools.weather_tools import get_weather

def route_tools_and_prompt(agent_id: str):
    """Router to map an agent ID to its required tools and prompt."""
    if agent_id.startswith("math"):
        return [add, multiply], "If John has 5 apples, buys 3 more, then multiplies his stash by 4, how many does he have? You MUST use the add and multiply tools."
    elif agent_id.startswith("fs"):
        return [list_files, read_file, write_file], "List the files in the current directory ('.'). Find the file named 'dummy_log.txt', read it, summarize the error you find, and write that summary into a new file called 'report.txt'."
    elif agent_id.startswith("world"):
        return [get_weather, search_web], "What is the current weather in Tokyo? After finding out, search the web for 'things to do in Tokyo when it is [insert weather condition here]'."
    return [], "Tell me a joke."

def main():
    print("Booting AgentOS...")
    
    # 1. Setup the OS Environment
    load_dotenv(override=True)
    db_path = "agentos.db"
    store = SQLiteStore(db_path=db_path)
    
    scheduler = TokenAwareScheduler(max_budget=1000)
    runtime = Runtime(store=store, scheduler=scheduler)
    
    # Create dummy file for fs_agent
    with open("dummy_log.txt", "w") as f:
        f.write("System OK. Error: Network timeout on port 8080. System OK.")

    # 2. Bootloader Recovery
    # This automatically scans the DB for orphaned RUNNING or soft-crashed FAILED agents,
    # rescues them to READY, and submits them to the Scheduler queue.
    runtime.bootstrap_recovery()

    # 3. Spawn New Work
    # We create 3 fresh agents for today's run and explicitly push them to the Scheduler.
    new_agents = ["math_agent", "fs_agent", "world_agent"]
    for i, role in enumerate(new_agents):
        agent_id = f"{role}_{int(time.time())}"
        task = Task(id=f"t_{agent_id}", description="True Tool-Calling loop", created_time=datetime.now())
        agent = Agent(agent_id=agent_id, task=task, priority=10 - i)
        agent.transition_to(AgentState.READY)
        store.save_agent(agent)
        
        print(f"[OS] Created New Agent: {agent_id}")
        scheduler.submit(agent)

    # 4. The OS Event Loop
    print("\n" + "="*50)
    print("--- OS EVENT LOOP START ---")
    print("="*50)
    
    while True:
        # Pull the next most important task from the Scheduler queue
        agent = scheduler.get_next()
        
        if not agent:
            print("[OS] Scheduler queue is completely empty. Idling...")
            break
            
        print(f"\n[OS] Scheduled to run: {agent.id}")
        tools, prompt = route_tools_and_prompt(agent.id)
        
        # Execute the agent blockingly
        # (In a true multi-threaded OS, we would submit this to a thread pool and continue the loop,
        # but for demonstration we run it here to respect rate limits cleanly).
        runtime.execute(
            agent_id=agent.id,
            agent_callable=lambda p=prompt, aid=agent.id, t=tools: tool_calling_agent_task(store, aid, p, t, simulate_crash=False),
            timeout=120
        )
        
        final_agent = store.load_agent(agent.id)
        print(f"[OS] Finished {agent.id} with State: {final_agent.state.name}")
        time.sleep(2) # Brief pause to respect API rate limits

    # 5. View the Results
    print("\n" + "="*50)
    print("AGENT EXECUTION COMPLETE")
    print("="*50)
    
    # We query ALL agents in the DB to prove we ran the old recovered ones too!
    all_agents = store.get_agents_by_state(AgentState.COMPLETED)
    all_agents.extend(store.get_agents_by_state(AgentState.FAILED))
    
    for agent in all_agents:
        print(f"\n--- {agent.id.upper()} ---")
        print(f"State: {agent.state.name} | Tokens Used: {agent.token_usage}")
        print(f"Execution History: {agent.execution_history}")
    
    print("\n" + "="*50)
    print(f"You can now open '{db_path}' in VS Code using the SQLite Viewer extension to see the tool calls saved permanently!")

if __name__ == "__main__":
    main()
