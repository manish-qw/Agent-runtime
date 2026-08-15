import sqlite3
import json
from datetime import datetime
from agentos.core.agent import Agent
from agentos.core.task import Task
from agentos.core.state import AgentState
from agentos.core.checkpoint import Checkpoint, CheckpointCorruptError

class SQLiteStore:
    def __init__(self, db_path: str = "agentos.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    tokens_used INTEGER NOT NULL DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    agent_id TEXT PRIMARY KEY,
                    checkpoint_data TEXT NOT NULL
                )
            """)
            conn.commit()

    def save_agent(self, agent: Agent):
        metadata = {
            "task": {
                "id": agent.task.id,
                "description": agent.task.description,
                "created_time": agent.task.created_time.isoformat()
            },
            "execution_history": agent.execution_history,
            "checkpoint_location": agent.checkpoint_location
        }
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agents (id, state, priority, created_at, metadata, tokens_used)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    state=excluded.state,
                    priority=excluded.priority,
                    metadata=excluded.metadata,
                    tokens_used=excluded.tokens_used
            """, (
                agent.id,
                agent.state.name,
                agent.priority,
                agent.created_time.isoformat(),
                json.dumps(metadata),
                agent.token_usage
            ))
            conn.commit()

    def update_state(self, agent_id: str, new_state: AgentState):
        """Updates only the state of an agent for faster atomic writes."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE agents SET state = ? WHERE id = ?", (new_state.name, agent_id))
            conn.commit()

    def load_agent(self, agent_id: str) -> Agent:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, state, priority, created_at, metadata, tokens_used FROM agents WHERE id = ?", (agent_id,))
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"Agent with id {agent_id} not found")
                
            db_id, db_state, db_priority, db_created_at, db_metadata, db_tokens_used = row
            metadata = json.loads(db_metadata)
            
            # Reconstruct Task
            task_data = metadata["task"]
            task = Task(
                id=task_data["id"],
                description=task_data["description"],
                created_time=datetime.fromisoformat(task_data["created_time"])
            )
            
            # Reconstruct Agent
            agent = Agent(agent_id=db_id, task=task, priority=db_priority)
            
            agent.state = AgentState[db_state]
            agent.created_time = datetime.fromisoformat(db_created_at)
            agent.execution_history = metadata.get("execution_history", [])
            agent.checkpoint_location = metadata.get("checkpoint_location")
            agent.token_usage = db_tokens_used
            
            return agent

    def save_checkpoint(self, checkpoint: Checkpoint):
        """Saves a checkpoint to the checkpoints table."""
        data = {
            "state": checkpoint.state.name,
            "conversation_history": checkpoint.conversation_history,
            "task_progress_marker": checkpoint.task_progress_marker,
            "timestamp": checkpoint.timestamp.isoformat()
        }
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO checkpoints (agent_id, checkpoint_data)
                VALUES (?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    checkpoint_data=excluded.checkpoint_data
            """, (checkpoint.agent_id, json.dumps(data)))
            conn.commit()

    def load_checkpoint(self, agent_id: str) -> Checkpoint:
        """Loads a checkpoint. Raises CheckpointCorruptError if JSON is malformed."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT checkpoint_data FROM checkpoints WHERE agent_id = ?", (agent_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
                
            try:
                data = json.loads(row[0])
                return Checkpoint(
                    agent_id=agent_id,
                    state=AgentState[data["state"]],
                    conversation_history=data.get("conversation_history", []),
                    task_progress_marker=data.get("task_progress_marker", "init"),
                    timestamp=datetime.fromisoformat(data["timestamp"])
                )
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                raise CheckpointCorruptError(f"Checkpoint for {agent_id} is corrupt: {str(e)}")
