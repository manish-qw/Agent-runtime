from enum import Enum, auto

class AgentState(Enum):
    CREATED = auto()
    READY = auto()
    RUNNING = auto()
    BLOCKED = auto()
    COMPLETED = auto()
    FAILED = auto()
