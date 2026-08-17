import os
import sys
import time
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

# Add the project root to sys.path so we can import agentos
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agentos.storage.sqlite_store import SQLiteStore
from agentos.core.state import AgentState
from agentos.core.agent import Agent
from agentos.core.task import Task
from agentos.runtime.engine import Runtime
from agentos.runtime.real_agents import tool_calling_agent_task

DB_PATH = "benchmarks/benchmark_1.db"

def process_data(step: int) -> str:
    """Use this tool exactly 10 times in sequential order from step=1 to step=10."""
    return f"Step {step} completed successfully. Proceed to the next step."

def setup_fresh_db():
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except PermissionError:
            pass
    return SQLiteStore(DB_PATH)

def run_trial(trial_num: int, strategy: str, crash_step: int = 7) -> dict:
    store = setup_fresh_db()
    runtime = Runtime(store)
    
    agent_id = f"b1_agent_{strategy}_{trial_num}"
    prompt = (
        "You are a sequential processor. You MUST use the `process_data` tool exactly 10 times in a row. "
        "Call it with step=1, then step=2, up to step=10. Once step 10 is complete, output 'TASK FINISHED'."
    )
    tools = [process_data]
    
    # Setup initial agent
    task = Task(id=f"t_{agent_id}", description="10-step chain", created_time=datetime.now())
    agent = Agent(agent_id=agent_id, task=task)
    agent.transition_to(AgentState.READY)
    store.save_agent(agent)
    
    total_tokens = 0
    start_time = time.time()
    
    # 1. Run until crash
    try:
        runtime.execute(
            agent_id=agent_id,
            agent_callable=lambda: tool_calling_agent_task(store, agent_id, prompt, tools, crash_at_tool_call=crash_step),
            timeout=120
        )
    except Exception as e:
        pass # Expected crash
        
    crashed_agent = store.load_agent(agent_id)
    total_tokens += crashed_agent.token_usage
    
    if strategy == "cold_restart":
        # WIPE AND START OVER
        store = setup_fresh_db()
        runtime = Runtime(store)
        agent = Agent(agent_id=agent_id, task=task)
        agent.transition_to(AgentState.READY)
        store.save_agent(agent)
        
        runtime.execute(
            agent_id=agent_id,
            agent_callable=lambda: tool_calling_agent_task(store, agent_id, prompt, tools, crash_at_tool_call=0),
            timeout=120
        )
        
        final_agent = store.load_agent(agent_id)
        total_tokens += final_agent.token_usage
        
    elif strategy == "checkpoint_resume":
        # RESUME FROM CHECKPOINT
        runtime.bootstrap_recovery()
        
        runtime.execute(
            agent_id=agent_id,
            agent_callable=lambda: tool_calling_agent_task(store, agent_id, prompt, tools, crash_at_tool_call=0),
            timeout=120
        )
        
        final_agent = store.load_agent(agent_id)
        total_tokens = final_agent.token_usage
        
    wall_clock_time = time.time() - start_time
    
    return {
        "trial_num": trial_num,
        "strategy": strategy,
        "tokens": total_tokens,
        "time": wall_clock_time
    }

def main():
    print("Starting Benchmark 1: Checkpoint Recovery Efficiency")
    
    # Warmup
    print("Running warmup...")
    run_trial(0, "checkpoint_resume", crash_step=2)
    
    results = []
    
    for i in range(1, 6):
        print(f"Trial {i}/5 - Cold Restart...")
        res_cold = run_trial(i, "cold_restart", crash_step=7)
        results.append(res_cold)
        print(f"  Cold Restart: {res_cold['time']:.2f}s, {res_cold['tokens']} tokens")
        
        print(f"Trial {i}/5 - Checkpoint Resume...")
        res_check = run_trial(i, "checkpoint_resume", crash_step=7)
        results.append(res_check)
        print(f"  Checkpoint Resume: {res_check['time']:.2f}s, {res_check['tokens']} tokens")

    df = pd.DataFrame(results)
    df.to_csv("benchmarks/b1_results.csv", index=False)
    
    print("\n=== FINAL RESULTS (Crash at Step 7/10) ===")
    summary = df.groupby("strategy").agg({
        "time": ["mean", "std"],
        "tokens": ["mean", "std"]
    })
    print(summary)
    
    cold_mean_time = summary.loc["cold_restart", ("time", "mean")]
    check_mean_time = summary.loc["checkpoint_resume", ("time", "mean")]
    
    cold_mean_tokens = summary.loc["cold_restart", ("tokens", "mean")]
    check_mean_tokens = summary.loc["checkpoint_resume", ("tokens", "mean")]
    
    time_saved = ((cold_mean_time - check_mean_time) / cold_mean_time) * 100
    tokens_saved = ((cold_mean_tokens - check_mean_tokens) / cold_mean_tokens) * 100
    
    print(f"\nCONCLUSION:")
    print(f"Checkpoint-based recovery reduced token consumption by {tokens_saved:.1f}% and completion time by {time_saved:.1f}% versus cold-restart, when recovering a crashed 10-step tool-calling agent (avg. of 5 runs, crash at step 7/10).")

if __name__ == "__main__":
    main()
