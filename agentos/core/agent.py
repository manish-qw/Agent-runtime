from .state import AgentState
from .task import Task
from datetime import datetime

class Agent:
    def __init__(self, agent_id: str, task: Task, priority: int = 0):
        self.id = agent_id
        self.task = task
        self.priority = priority
        self.state = AgentState.CREATED
        
        # PCB fields
        self.created_time = datetime.now()
        self.execution_history = []
        self.token_usage = 0
        self.checkpoint_location = None
        
        # Benchmark Metrics
        self.run_id = None
        self.scheduler_type = None
        self.submit_time = datetime.now()
        self.start_time = None
        self.end_time = None
        self.num_retries = 0
        self.checkpoint_count = 0

    def transition_to(self, new_state: AgentState):
        """Transitions the agent to a new state based on allowed rules."""
        # Define allowed transitions
        valid_transitions = {
            AgentState.CREATED: [AgentState.READY],
            AgentState.READY: [AgentState.RUNNING],
            AgentState.RUNNING: [AgentState.BLOCKED, AgentState.COMPLETED, AgentState.FAILED, AgentState.READY],
            AgentState.BLOCKED: [AgentState.READY],
            AgentState.COMPLETED: [],
            AgentState.FAILED: [AgentState.READY]  # Allow retry/resume
        }

        if new_state not in valid_transitions[self.state]:
            raise ValueError(f"Invalid state transition from {self.state.name} to {new_state.name}")
        
        self.state = new_state
