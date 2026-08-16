from typing import Callable, Any
import concurrent.futures
from datetime import datetime
from agentos.core.agent import Agent
from agentos.core.state import AgentState
from agentos.storage.sqlite_store import SQLiteStore
from agentos.scheduler.token_aware import TokenAwareScheduler

class Runtime:
    def __init__(self, store: SQLiteStore, max_workers: int = 10, scheduler=None):
        self.store = store
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.scheduler = scheduler

    def bootstrap_recovery(self):
        """
        Recovers orphaned agents if the main OS process crashed.
        - RUNNING/FAILED + Checkpoint exists -> READY (Resumable partial progress)
        - RUNNING + No Checkpoint -> FAILED (Nothing to recover)
        - READY -> Re-enqueues into scheduler
        """
        print("[OS BOOT] Checking for orphaned processes...")
        
        # Pass 1: Recover orphaned RUNNING agents (hard crash) and FAILED agents (soft crash)
        orphaned_agents = self.store.get_agents_by_state(AgentState.RUNNING)
        orphaned_agents.extend(self.store.get_agents_by_state(AgentState.FAILED))
        
        for agent in orphaned_agents:
            checkpoint = self.store.load_checkpoint(agent.id)
            if checkpoint and checkpoint.conversation_history:
                print(f"[OS BOOT] Recovering {agent.id} (Checkpoint found) -> READY")
                agent.transition_to(AgentState.READY)
                agent.execution_history.append(f"OS Boot: Recovered from {agent.state.name} to READY")
                self.store.save_agent(agent)
            elif agent.state == AgentState.RUNNING:
                print(f"[OS BOOT] Terminating {agent.id} (No Checkpoint) -> FAILED")
                agent.transition_to(AgentState.FAILED)
                agent.end_time = datetime.now()
                agent.execution_history.append("OS Boot: Fatal crash with no checkpoint")
                self.store.save_agent(agent)
            
        # Pass 2: Re-enqueue READY agents
            
        if self.scheduler:
            ready_agents = self.store.get_agents_by_state(AgentState.READY)
            for agent in ready_agents:
                print(f"[OS BOOT] Re-queueing {agent.id} into Scheduler")
                self.scheduler.submit(agent)

    def execute(self, agent_id: str, agent_callable: Callable, timeout: int = 5) -> Any:
        """Executes an agent's task with a timeout and state isolation."""
        
        # Load fresh state from DB
        agent = self.store.load_agent(agent_id)
        
        # Track start time for benchmarking if this is the first execution
        if not agent.start_time:
            agent.start_time = datetime.now()
        
        # Transition to RUNNING
        agent.transition_to(AgentState.RUNNING)
        agent.execution_history.append("Started execution")
        self.store.save_agent(agent)

        try:
            # Submit to thread pool
            future = self.executor.submit(agent_callable)
            
            # Wait for result with strict timeout
            result = future.result(timeout=timeout)
            
            if result == "YIELD":
                # Agent yielded control cooperatively
                agent.transition_to(AgentState.READY)
                agent.execution_history.append("Yielded control")
                self.store.save_agent(agent)
                if self.scheduler:
                    self.scheduler.update(agent)
                return result

            # On success, check if result is a tuple (response, token_count)
            final_result = result
            if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
                final_result, tokens_used = result
                agent.token_usage += tokens_used
                agent.execution_history.append(f"Used {tokens_used} tokens")

            agent.transition_to(AgentState.COMPLETED)
            agent.end_time = datetime.now()
            agent.execution_history.append(f"Completed successfully: {final_result}")
            self.store.save_agent(agent)
            
            if self.scheduler and hasattr(self.scheduler, 'complete_agent'):
                self.scheduler.complete_agent(agent)
                
            return final_result
            
        except concurrent.futures.TimeoutError:
            # Handle hung task (timeout)
            agent.transition_to(AgentState.FAILED)
            agent.end_time = datetime.now()
            agent.execution_history.append(f"Failed: Execution timed out after {timeout}s")
            self.store.save_agent(agent)
            if self.scheduler and hasattr(self.scheduler, 'complete_agent'):
                self.scheduler.complete_agent(agent)
            return None
            
        except Exception as e:
            # Handle crash isolation
            agent.transition_to(AgentState.FAILED)
            agent.end_time = datetime.now()
            agent.execution_history.append(f"Failed: Exception raised - {str(e)}")
            self.store.save_agent(agent)
            if self.scheduler and hasattr(self.scheduler, 'complete_agent'):
                self.scheduler.complete_agent(agent)
            return None
