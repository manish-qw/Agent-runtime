import os
import sys
import time
import threading
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agentos.storage.sqlite_store import SQLiteStore
from agentos.core.state import AgentState
from agentos.core.agent import Agent
from agentos.core.task import Task
from agentos.runtime.engine import Runtime
from agentos.scheduler.fifo import FIFOScheduler
from agentos.runtime.dummy_agents import sleep_agent, exception_agent

DB_PATH = "benchmarks/benchmark_3.db"

def setup_fresh_db(db_path: str):
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except PermissionError:
            pass
    return SQLiteStore(db_path)

def run_fault_isolation_benchmark():
    print("Starting Benchmark 3: Fault Isolation & Reliability")
    store = setup_fresh_db(DB_PATH)
    
    # We will use FIFOScheduler for simple dispatch
    scheduler = FIFOScheduler()
    runtime = Runtime(store, max_workers=10, scheduler=scheduler)
    
    total_agents = 1000
    crash_rate = 0.30 # 20% crash rate
    num_crashing = int(total_agents * crash_rate)
    num_healthy = total_agents - num_crashing
    
    print(f"Submitting {total_agents} agents total.")
    print(f" - {num_healthy} healthy agents")
    print(f" - {num_crashing} poison-pill agents (intentionally crash with RuntimeError)")
    
    agents = []
    import random
    # Randomly select exact indices for the poison agents to perfectly match crash_rate
    poison_indices = set(random.sample(range(total_agents), num_crashing))
    
    for i in range(total_agents):
        is_poison = (i in poison_indices)
        
        agent_id = f"b3_a{i}_{'poison' if is_poison else 'healthy'}"
        task = Task(id=f"t_{agent_id}", description="Fault Isolation Test", created_time=datetime.now())
        agent = Agent(agent_id=agent_id, task=task)
        agent.transition_to(AgentState.READY)
        store.save_agent(agent)
        agents.append((agent, is_poison))
        scheduler.submit(agent)
        
    start_time = time.time()
    
    exit_flag = [False]
    
    # Start the daemon workers exactly like previous benchmarks
    def worker_loop():
        while not exit_flag[0]:
            agent_record = scheduler.get_next()
            if not agent_record:
                time.sleep(0.1)
                continue
            
            # Determine which callable to use based on agent ID
            is_poison = "poison" in agent_record.id
            callable_fn = exception_agent if is_poison else lambda: sleep_agent(0.5)
            
            # runtime.execute internally wraps the execution in a try/except to catch crashes
            # and transition the agent to FAILED without crashing the worker thread itself.
            runtime.execute(
                agent_id=agent_record.id,
                agent_callable=callable_fn,
                timeout=5
            )

    threads = []
    for _ in range(10): # 10 worker threads
        t = threading.Thread(target=worker_loop, daemon=True)
        t.start()
        threads.append(t)
        
    # Monitor progress
    while True:
        completed = store.get_agents_by_state(AgentState.COMPLETED)
        failed = store.get_agents_by_state(AgentState.FAILED)
        if len(completed) + len(failed) >= total_agents:
            break
        time.sleep(1)
        print(f"  Progress: {len(completed)} completed, {len(failed)} failed out of {total_agents} total...")
        
    exit_flag[0] = True
    end_time = time.time()
    
    completed = store.get_agents_by_state(AgentState.COMPLETED)
    failed = store.get_agents_by_state(AgentState.FAILED)
    
    total_completed = len(completed)
    total_failed = len(failed)
    
    expected_failed = num_crashing
    expected_completed = num_healthy
    
    print("\n==============================")
    print("=== FAULT ISOLATION RESULTS ===")
    print("==============================")
    print(f"Total Agents: {total_agents}")
    print(f"Injected Faults (Expected Failed): {expected_failed}")
    print(f"Actual Failed: {total_failed}")
    print(f"Expected Completed: {expected_completed}")
    print(f"Actual Completed: {total_completed}")
    print(f"Time Taken: {end_time - start_time:.2f}s")
    
    if total_completed == expected_completed and total_failed == expected_failed:
        print("\nCONCLUSION:")
        print("SUCCESS! AgentOS isolated 100% of injected faults.")
        print(f"The OS event loop remained 100% stable, ensuring exactly {total_completed} sibling agents completed their work undisturbed despite {total_failed} concurrent runtime crashes.")
    else:
        print("\nCONCLUSION:")
        print("FAILURE! The OS did not properly isolate the faults.")
        
    # Write to a CSV just to maintain uniformity
    df = pd.DataFrame([{
        "total_agents": total_agents,
        "injected_faults": expected_failed,
        "actual_failed": total_failed,
        "expected_completed": expected_completed,
        "actual_completed": total_completed,
        "time": end_time - start_time
    }])
    df.to_csv("benchmarks/b3_results_isolation.csv", index=False)

if __name__ == "__main__":
    run_fault_isolation_benchmark()
