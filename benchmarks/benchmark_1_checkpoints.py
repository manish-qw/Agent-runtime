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
from agentos.tools.math_tools import add, multiply
from agentos.tools.weather_tools import get_weather
from agentos.tools.web_tools import search_web

DB_PATH = "benchmarks/benchmark_1.db"

def setup_fresh_db():
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except PermissionError:
            pass
    return SQLiteStore(DB_PATH)

def run_trial(trial_num: int, strategy: str, task_name: str, prompt: str, tools: list, crash_step: int = 7) -> dict:
    store = setup_fresh_db()
    runtime = Runtime(store)
    
    agent_id = f"b1_{task_name}_{strategy}_{trial_num}"
    # Setup initial agent
    task = Task(id=f"t_{agent_id}", description=f"10-step {task_name}", created_time=datetime.now())
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

def run_task_benchmark(task_name: str, prompt: str, tools: list):
    print(f"\n=======================================================")
    print(f"Starting Benchmark 1 for Task: {task_name.upper()}")
    print(f"=======================================================")
    
    # Warmup
    print("Running warmup...")
    run_trial(0, "checkpoint_resume", task_name, prompt, tools, crash_step=2)
    
    results = []
    
    for i in range(1, 6):
        print(f"Trial {i}/5 - Cold Restart...")
        res_cold = run_trial(i, "cold_restart", task_name, prompt, tools, crash_step=7)
        results.append(res_cold)
        print(f"  Cold Restart: {res_cold['time']:.2f}s, {res_cold['tokens']} tokens")
        
        print(f"Trial {i}/5 - Checkpoint Resume...")
        res_check = run_trial(i, "checkpoint_resume", task_name, prompt, tools, crash_step=7)
        results.append(res_check)
        print(f"  Checkpoint Resume: {res_check['time']:.2f}s, {res_check['tokens']} tokens")

    df = pd.DataFrame(results)
    csv_path = f"benchmarks/b1_results_{task_name}.csv"
    df.to_csv(csv_path, index=False)
    
    print(f"\n=== FINAL RESULTS FOR {task_name.upper()} ===")
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
    
    print(f"\nCONCLUSION ({task_name}):")
    print(f"Checkpoint-based recovery reduced token consumption by {tokens_saved:.1f}% and completion time by {time_saved:.1f}% versus cold-restart.")
    print(f"Results saved to {csv_path}")

import argparse

def main():
    parser = argparse.ArgumentParser(description="Run Benchmark 1")
    parser.add_argument("--task", type=str, choices=["math", "weather", "search"], required=True, help="Which task to run")
    args = parser.parse_args()

    math_prompt = (
        "Calculate the result of the following 10 mathematical operations sequentially. "
        "You MUST use the `add` and `multiply` tools to compute the answers. Do not do the math in your head.\n"
        "1. Multiply 12 by 15\n"
        "2. Add 55 to the result of step 1\n"
        "3. Multiply the result of step 2 by 4\n"
        "4. Add 123 to the result of step 3\n"
        "5. Multiply the result of step 4 by 7\n"
        "6. Add 999 to the result of step 5\n"
        "7. Multiply the result of step 6 by 3\n"
        "8. Add 456 to the result of step 7\n"
        "9. Multiply the result of step 8 by 2\n"
        "10. Add 777 to the result of step 9\n"
        "After completing all 10 steps using the tools, output the final answer."
    )
    
    weather_prompt = (
        "You must find the current weather for the following 10 cities sequentially. "
        "You MUST use the `get_weather` tool exactly 10 times, one for each city.\n"
        "1. Mumbai, India\n"
        "2. Delhi, India\n"
        "3. Bangalore, India\n"
        "4. Hyderabad, India\n"
        "5. Ahmedabad, India\n"
        "6. Chennai, India\n"
        "7. Kolkata, India\n"
        "8. Surat, India\n"
        "9. Pune, India\n"
        "10. Jaipur, India\n"
        "After completing all 10 steps using the tool, output a short summary of the weather."
    )
    
    search_prompt = (
        "You must search the web for the following 10 queries sequentially. "
        "You MUST use the `search_web` tool exactly 10 times, one for each query.\n"
        "1. Who is the CEO of Google?\n"
        "2. What is the capital of France?\n"
        "3. Who won the 2022 FIFA World Cup?\n"
        "4. What is the population of Tokyo?\n"
        "5. Who wrote the play Hamlet?\n"
        "6. What is the tallest mountain in the world?\n"
        "7. Who discovered Penicillin?\n"
        "8. What is the currency of Japan?\n"
        "9. When did the Apollo 11 moon landing happen?\n"
        "10. What is the speed of light?\n"
        "After completing all 10 searches using the tool, output a short summary of what you found."
    )
    
    if args.task == "math":
        run_task_benchmark("math", math_prompt, [add, multiply])
    elif args.task == "weather":
        run_task_benchmark("weather", weather_prompt, [get_weather])
    elif args.task == "search":
        run_task_benchmark("search", search_prompt, [search_web])

if __name__ == "__main__":
    main()
