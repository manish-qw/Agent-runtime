import os
import sys
import time
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agentos.storage.sqlite_store import SQLiteStore
from agentos.core.state import AgentState
from agentos.core.agent import Agent
from agentos.core.task import Task
from agentos.runtime.engine import Runtime
from agentos.runtime.real_agents import tool_calling_agent_task
from agentos.tools.math_tools import add, multiply
from agentos.scheduler.fifo import FIFOScheduler
from agentos.scheduler.priority import PriorityScheduler
from agentos.scheduler.token_aware import TokenAwareScheduler

DB_PATH = "benchmarks/benchmark_2.db"

def setup_fresh_db():
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except PermissionError:
            pass
    return SQLiteStore(DB_PATH)

def run_scheduler_trial(trial_num: int, scheduler_name: str) -> dict:
    store = setup_fresh_db()
    
    if scheduler_name == "fifo":
        scheduler = FIFOScheduler()
    elif scheduler_name == "priority":
        scheduler = PriorityScheduler()
    elif scheduler_name == "token_aware":
        # Limit to 3 concurrent agents (assuming 100 estimated tokens per step in the scheduler)
        scheduler = TokenAwareScheduler(max_budget=350)
    
    # We use max_workers=20 to intentionally cause Vertex AI rate limits (429s) if the scheduler doesn't throttle
    runtime = Runtime(store, max_workers=20, scheduler=scheduler)
    
    # We use a 3-step math task to keep costs reasonable, but still hit limits with 30 agents
    prompt = (
        "Calculate the result sequentially: "
        "1. Add 100 to 200\n"
        "2. Multiply the result by 5\n"
        "3. Add 400 to the result.\n"
        "Output the final answer."
    )
    tools = [add, multiply]
    
    start_time = time.time()
    
    # Create 30 agents (25 low priority, 5 high priority)
    agents = []
    for i in range(30):
        priority = 10 if i < 5 else 0 # First 5 are High priority agents
        agent_id = f"b2_{scheduler_name}_t{trial_num}_a{i}"
        
        task = Task(id=f"t_{agent_id}", description="3-step math", created_time=datetime.now())
        agent = Agent(agent_id=agent_id, task=task, priority=priority)
        agent.transition_to(AgentState.READY)
        store.save_agent(agent)
        agents.append(agent)
        
    # Submit all to scheduler
    for agent in agents:
        scheduler.submit(agent)
        
    # Run the worker loop manually to feed threads from the scheduler
    import threading
    
    def worker_loop():
        while True:
            agent = scheduler.get_next()
            if not agent:
                # If no agents are ready, sleep briefly
                time.sleep(0.5)
                # Check if all agents are done to terminate thread gracefully
                if len(store.get_agents_by_state(AgentState.COMPLETED)) + len(store.get_agents_by_state(AgentState.FAILED)) == 30:
                    break
                continue
            
            # Execute agent (catches exceptions internally)
            runtime.execute(
                agent_id=agent.id,
                agent_callable=lambda a_id=agent.id: tool_calling_agent_task(store, a_id, prompt, tools, crash_at_tool_call=0),
                timeout=120
            )

    threads = []
    for _ in range(20):
        t = threading.Thread(target=worker_loop, daemon=True)
        t.start()
        threads.append(t)
        
    # Wait for all agents to complete
    while True:
        completed = store.get_agents_by_state(AgentState.COMPLETED)
        failed = store.get_agents_by_state(AgentState.FAILED)
        if len(completed) + len(failed) == 30:
            break
        time.sleep(2)
        print(f"  Progress: {len(completed) + len(failed)}/30 agents completed...")
        
    end_time = time.time()
    
    # Analyze high-priority completion times
    high_pri_times = []
    for agent in agents[:5]:
        updated_agent = store.load_agent(agent.id)
        if updated_agent.end_time and updated_agent.start_time:
            high_pri_times.append((updated_agent.end_time - updated_agent.start_time).total_seconds())
            
    p95_high_pri = np.percentile(high_pri_times, 95) if high_pri_times else 0
    
    # We rely on throughput degradation to measure the impact of rate limits
    # If FIFO hits rate limits, tenacity will pause threads, reducing overall throughput.
    
    return {
        "trial_num": trial_num,
        "scheduler": scheduler_name,
        "total_time": end_time - start_time,
        "p95_high_pri_time": p95_high_pri
    }

def main():
    print("Starting Benchmark 2: Scheduler Comparison Under Token Budget")
    print("This will submit 30 agents to Vertex AI concurrently using 3 different schedulers.")
    
    results = []
    for sched in ["fifo", "priority", "token_aware"]:
        print(f"\n==============================")
        print(f"Testing Scheduler: {sched.upper()}")
        print(f"==============================")
        for i in range(1, 4):
            print(f"Running Trial {i}/3...")
            res = run_scheduler_trial(i, sched)
            results.append(res)
            print(f"  Result: {res['total_time']:.2f}s | P95 High-Pri: {res['p95_high_pri_time']:.2f}s")
            
    df = pd.DataFrame(results)
    csv_path = "benchmarks/b2_results.csv"
    df.to_csv(csv_path, index=False)
    
    print("\n=== FINAL RESULTS ===")
    summary = df.groupby("scheduler").agg({
        "total_time": ["mean", "std"],
        "p95_high_pri_time": ["mean", "std"]
    })
    print(summary)
    
    fifo_time = summary.loc["fifo", ("total_time", "mean")]
    token_time = summary.loc["token_aware", ("total_time", "mean")]
    
    fifo_p95 = summary.loc["fifo", ("p95_high_pri_time", "mean")]
    token_p95 = summary.loc["token_aware", ("p95_high_pri_time", "mean")]
    
    time_saved = ((fifo_time - token_time) / fifo_time) * 100
    p95_saved = ((fifo_p95 - token_p95) / fifo_p95) * 100
    
    print(f"\nCONCLUSION:")
    print(f"TokenAware scheduling improved overall throughput time by {time_saved:.1f}%")
    print(f"It also improved P95 completion time for High-Priority agents by {p95_saved:.1f}% versus FIFO.")
    print(f"Results saved to {csv_path}")

if __name__ == "__main__":
    main()
