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
from agentos.runtime.real_agents import multi_step_research_agent_task
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
    # 2. Setup 2 concurrent multi-step tasks
    documents = [
        ("researcher_os", "Operating systems manage computer hardware, software resources, and provide common services for computer programs. Time-sharing operating systems schedule tasks for efficient use of the system and may also include accounting software for cost allocation of processor time, mass storage, memory, and printing services."),
        ("researcher_ai", "Artificial intelligence (AI) is intelligence demonstrated by machines, as opposed to intelligence of humans and other animals. AI applications include advanced web search engines, recommendation systems, understanding human speech, self-driving cars, and generative or creative tools.")
    ]

    agent_ids = []
    for i, (role, doc) in enumerate(documents):
        agent_id = f"{role}_{int(time.time())}"
        agent_ids.append(agent_id)
        task = Task(id=f"t_{agent_id}", description="Multi-step OS/AI research", created_time=datetime.now())
        agent = Agent(agent_id=agent_id, task=task, priority=10 - i)
        agent.transition_to(AgentState.READY)
        store.save_agent(agent)
        print(f"Created Agent [{agent_id}]")

    # 3. Execute the Agents Concurrently
    print(f"\nDispatching 2 multi-step agents to Gemini API concurrently...")
    print("Each agent will internally make 2 sequential API calls (Step 1: Keywords, Step 2: Summary).")
    print("Because they save progress to SQLite in between, they can survive crashes!")
    print("This may take 10-15 seconds...\n")
    
    import concurrent.futures
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_to_id = {}
        for (role, doc), agent_id in zip(documents, agent_ids):
            # multi_step_research_agent_task requires (client, store, agent_id, document)
            future = executor.submit(
                runtime.execute, 
                agent_id, 
                lambda d=doc, aid=agent_id: multi_step_research_agent_task(client, store, aid, d), 
                60 # Increased timeout because it makes 2 LLM calls!
            )
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
