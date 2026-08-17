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
from unittest.mock import patch
from google.genai.models import Models
from google.genai.errors import APIError
import argparse

DB_PATH = "benchmarks/benchmark_2.db"

def setup_fresh_db(db_path: str):
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except PermissionError:
            pass
    return SQLiteStore(db_path)

def run_scheduler_trial(trial_num: int, scheduler_name: str) -> dict:
    db_path = f"benchmarks/benchmark_2_{scheduler_name}_{trial_num}.db"
    store = setup_fresh_db(db_path)
    
    if scheduler_name == "fifo":
        scheduler = FIFOScheduler()
    elif scheduler_name == "priority":
        scheduler = PriorityScheduler()
    elif scheduler_name == "token_aware":
        # Limit to 10 concurrent agents (assuming 100 estimated tokens per step in the scheduler)
        scheduler = TokenAwareScheduler(max_budget=1000)
    
    # We use a fair baseline of max_workers=20 for all schedulers.
    # FIFOScheduler will use all 20 threads (naive bounding).
    # TokenAwareScheduler will internally throttle below 20 to respect its token budget.
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
    
    # Create 100 agents (80 low priority, 20 high priority)
    agents = []
    for i in range(100):
        priority = 10 if i < 20 else 0 # First 20 are High priority agents
        agent_id = f"b2_{scheduler_name}_t{trial_num}_a{i}"
        
        task = Task(id=f"t_{agent_id}", description="3-step math", created_time=datetime.now())
        agent = Agent(agent_id=agent_id, task=task, priority=priority)
        agent.transition_to(AgentState.READY)
        store.save_agent(agent)
        agents.append(agent)
        
    # Submit all to scheduler
    for agent in agents:
        scheduler.submit(agent)
        
    rate_limit_hits = [0]
    original_generate_content = Models.generate_content
    
    def count_429s_and_generate(self, *args, **kwargs):
        try:
            return original_generate_content(self, *args, **kwargs)
        except APIError as e:
            if e.code == 429:
                rate_limit_hits[0] += 1
            raise e
            
    # Run the worker loop manually to feed threads from the scheduler
    import threading
    
    exit_flag = [False]
    
    def worker_loop():
        while not exit_flag[0]:
            agent = scheduler.get_next()
            if not agent:
                # If no agents are ready, sleep briefly
                time.sleep(0.5)
                continue
            
            # Execute agent (catches exceptions internally)
            with patch('google.genai.models.Models.generate_content', new=count_429s_and_generate):
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
        if len(completed) + len(failed) >= 100:
            break
        time.sleep(2)
        print(f"  Progress: {len(completed) + len(failed)}/100 agents completed...")
        
    exit_flag[0] = True
    end_time = time.time()
    
    # Analyze high-priority completion times
    high_pri_times = []
    for agent in agents[:20]:
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
        "p95_high_pri_time": p95_high_pri,
        "rate_limit_errors": rate_limit_hits[0]
    }

def main():
    parser = argparse.ArgumentParser(description="Run Benchmark 2")
    parser.add_argument("--scheduler", type=str, choices=["fifo", "priority", "token_aware"], required=True, help="Which scheduler to test")
    args = parser.parse_args()
    
    print("Starting Benchmark 2: Scheduler Comparison Under Token Budget")
    print(f"This will submit 100 agents to Vertex AI concurrently using the {args.scheduler.upper()} scheduler.")
    
    results = []
    print(f"\n==============================")
    print(f"Testing Scheduler: {args.scheduler.upper()}")
    print(f"==============================")
    for i in range(1, 4):
        print(f"Running Trial {i}/3...")
        res = run_scheduler_trial(i, args.scheduler)
        results.append(res)
        print(f"  Result: {res['total_time']:.2f}s | P95 High-Pri: {res['p95_high_pri_time']:.2f}s | 429 Errors Caught: {res['rate_limit_errors']}")
            
    df = pd.DataFrame(results)
    csv_path = f"benchmarks/b2_results_{args.scheduler}.csv"
    df.to_csv(csv_path, index=False)
    
    print(f"\n=== FINAL RESULTS FOR {args.scheduler.upper()} ===")
    summary = df.groupby("scheduler").agg({
        "total_time": ["mean", "std"],
        "p95_high_pri_time": ["mean", "std"],
        "rate_limit_errors": ["mean"]
    })
    print(summary)
    print(f"Results saved to {csv_path}")

if __name__ == "__main__":
    main()
