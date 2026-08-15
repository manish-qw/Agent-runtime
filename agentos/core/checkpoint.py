from dataclasses import dataclass, field
from datetime import datetime
from typing import List
from agentos.core.state import AgentState

class CheckpointCorruptError(Exception):
    """Raised when a checkpoint JSON blob is malformed or invalid."""
    pass

@dataclass
class Checkpoint:
    agent_id: str
    state: AgentState
    conversation_history: List[str] = field(default_factory=list)
    task_progress_marker: str = "init"
    timestamp: datetime = field(default_factory=datetime.now)
