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
from agentos.scheduler.token_aware import TokenAwareScheduler

def main():
    # 1. Setup the OS Environment
    print("Booting AgentOS...")
    load_dotenv()
    
    # We will use a permanent database so you can inspect it anytime!
    db_path = "agentos.db"
    store = SQLiteStore(db_path=db_path)
    
    # Initialize the Scheduler and Runtime engine
    scheduler = TokenAwareScheduler(max_budget=50)
    runtime = Runtime(store=store, scheduler=scheduler)
    client = GeminiLLMClient()

    # 2. Setup 4 concurrent tasks
    tasks = [
        ("coder_1", coding_agent_task, "Write a Python script for Fibonacci up to 10. Give code only in C++."),
        ("coder_2", coding_agent_task, "Write a Python function to calculate factorial. Give code only in C++."),
        ("researcher_1", research_agent_task, "Summarize what an operating system scheduler does in 4 sentences."),
        ("researcher_2", research_agent_task, "Explain what a Process Control Block (PCB) is in 4 sentences.")
    ]

    agent_ids = []
    for i, (role, func, prompt) in enumerate(tasks):
        agent_id = f"{role}_{int(time.time())}"
        agent_ids.append(agent_id)
        task = Task(id=f"t_{agent_id}", description=prompt, created_time=datetime.now())
        agent = Agent(agent_id=agent_id, task=task, priority=10 - i)
        agent.transition_to(AgentState.READY)
        store.save_agent(agent)
        print(f"Created Agent [{agent_id}]")

    # 3. Execute the Agents Concurrently
    print(f"\nDispatching 4 agents to Gemini API concurrently (this may take a few seconds)...")
    
    import concurrent.futures
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_id = {}
        for (role, func, prompt), agent_id in zip(tasks, agent_ids):
            future = executor.submit(runtime.execute, agent_id, lambda f=func, p=prompt: f(client, p), 30)
            future_to_id[future] = agent_id
            
        for future in concurrent.futures.as_completed(future_to_id):
            agent_id = future_to_id[future]
            try:
                results[agent_id] = future.result()
            except Exception as e:
                results[agent_id] = f"Failed: {str(e)}"
    
    # 4. View the Results
    print("\n" + "="*50)
    print("AGENT EXECUTION COMPLETE")
    print("="*50)
    
    for agent_id in agent_ids:
        final_agent = store.load_agent(agent_id)
        print(f"\n--- {agent_id.upper()} ---")
        print(f"State: {final_agent.state.name} | Tokens Used: {final_agent.token_usage}")
        print(results[agent_id])
    
    print("\n" + "="*50)
    print(f"You can now open '{db_path}' in VS Code using the SQLite Viewer extension to see this data permanently stored in the 'agents' table!")

if __name__ == "__main__":
    main()
