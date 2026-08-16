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

    def _get_connection(self):
        """Returns a configured SQLite connection with WAL mode enabled for high concurrency."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        # NOTE: SQLite's internal WAL "checkpointing" (flushing WAL to the main DB file) 
        # is entirely distinct from our app-level `Checkpoint` dataclass (agent progress snapshots).
        # Do not confuse the two when reading SQLite debug logs!
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
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
            "checkpoint_location": agent.checkpoint_location,
            "run_id": agent.run_id,
            "scheduler_type": agent.scheduler_type,
            "submit_time": agent.submit_time.isoformat() if agent.submit_time else None,
            "start_time": agent.start_time.isoformat() if agent.start_time else None,
            "end_time": agent.end_time.isoformat() if agent.end_time else None,
            "num_retries": agent.num_retries,
            "checkpoint_count": agent.checkpoint_count
        }
        
        with self._get_connection() as conn:
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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE agents SET state = ? WHERE id = ?", (new_state.name, agent_id))
            conn.commit()

    def load_agent(self, agent_id: str) -> Agent:
        with self._get_connection() as conn:
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
            agent.run_id = metadata.get("run_id")
            agent.scheduler_type = metadata.get("scheduler_type")
            
            # Helper for safe parsing
            def parse_dt(dt_str):
                return datetime.fromisoformat(dt_str) if dt_str else None
                
            agent.submit_time = parse_dt(metadata.get("submit_time"))
            agent.start_time = parse_dt(metadata.get("start_time"))
            agent.end_time = parse_dt(metadata.get("end_time"))
            
            agent.num_retries = metadata.get("num_retries", 0)
            agent.checkpoint_count = metadata.get("checkpoint_count", 0)
            
            agent.token_usage = db_tokens_used
            
            return agent

    def get_agents_by_state(self, state: AgentState) -> list[Agent]:
        """Returns a list of all agents currently in the specified state."""
        agents = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM agents WHERE state = ?", (state.name,))
            rows = cursor.fetchall()
            for row in rows:
                agents.append(self.load_agent(row[0]))
        return agents

    def save_checkpoint(self, checkpoint: Checkpoint):
        """Saves a checkpoint to the checkpoints table."""
        # Increment the parent agent's checkpoint_count for benchmark metrics
        agent = self.load_agent(checkpoint.agent_id)
        agent.checkpoint_count += 1
        self.save_agent(agent)
        
        data = {
            "state": checkpoint.state.name,
            "conversation_history": checkpoint.conversation_history,
            "task_progress_marker": checkpoint.task_progress_marker,
            "timestamp": checkpoint.timestamp.isoformat()
        }
        with self._get_connection() as conn:
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
        with self._get_connection() as conn:
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
