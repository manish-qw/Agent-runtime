from dataclasses import dataclass
from datetime import datetime

@dataclass
class Task:
    id: str
    description: str
    created_time: datetime
