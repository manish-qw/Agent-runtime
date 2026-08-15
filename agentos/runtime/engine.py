from typing import Callable, Any
import concurrent.futures
from agentos.core.agent import Agent
from agentos.core.state import AgentState
from agentos.storage.sqlite_store import SQLiteStore
from agentos.scheduler.token_aware import TokenAwareScheduler

class Runtime:
    def __init__(self, store: SQLiteStore, max_workers: int = 10, scheduler=None):
        self.store = store
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.scheduler = scheduler

    def execute(self, agent_id: str, agent_callable: Callable, timeout: int = 5) -> Any:
        """Executes an agent's task with a timeout and state isolation."""
        
        # Load fresh state from DB
        agent = self.store.load_agent(agent_id)
        
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
            agent.execution_history.append(f"Completed successfully: {final_result}")
            self.store.save_agent(agent)
            
            if self.scheduler and hasattr(self.scheduler, 'complete_agent'):
                self.scheduler.complete_agent(agent)
                
            return final_result
            
        except concurrent.futures.TimeoutError:
            # Handle hung task (timeout)
            agent.transition_to(AgentState.FAILED)
            agent.execution_history.append(f"Failed: Execution timed out after {timeout}s")
            self.store.save_agent(agent)
            if self.scheduler and hasattr(self.scheduler, 'complete_agent'):
                self.scheduler.complete_agent(agent)
            return None
            
        except Exception as e:
            # Handle crash isolation
            agent.transition_to(AgentState.FAILED)
            agent.execution_history.append(f"Failed: Exception raised - {str(e)}")
            self.store.save_agent(agent)
            if self.scheduler and hasattr(self.scheduler, 'complete_agent'):
                self.scheduler.complete_agent(agent)
            return None
