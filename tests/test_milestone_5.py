import pytest
import sqlite3
import json
from datetime import datetime
from agentos.core.agent import Agent
from agentos.core.task import Task
from agentos.core.state import AgentState
from agentos.core.checkpoint import Checkpoint, CheckpointCorruptError
from agentos.runtime.engine import Runtime

from agentos.llm.client import MockLLMClient

def test_save_load_checkpoint(store):
    """Test 1: Save/Load test. Checkpoint a RUNNING agent mid-task, simulate kill, reload."""
    agent_id = "agent_m5_1"
    
    # 0. Create the agent first!
    task = Task("t_m5_1", "Test task", datetime.now())
    agent = Agent(agent_id, task)
    agent.state = AgentState.RUNNING
    store.save_agent(agent)
    
    # 1. Create and save a checkpoint
    ckpt = Checkpoint(
        agent_id=agent_id,
        state=AgentState.RUNNING,
        conversation_history=["Step 1 complete", "Step 2 started"],
        task_progress_marker="step_2"
    )
    store.save_checkpoint(ckpt)
    
    # 2. Simulate kill (drop store and recreate)
    db_path = store.db_path
    del store
    from agentos.storage.sqlite_store import SQLiteStore
    new_store = SQLiteStore(db_path=db_path)
    
    # 3. Reload and assert
    loaded_ckpt = new_store.load_checkpoint(agent_id)
    assert loaded_ckpt is not None
    assert loaded_ckpt.agent_id == agent_id
    assert loaded_ckpt.state == AgentState.RUNNING
    assert loaded_ckpt.task_progress_marker == "step_2"
    assert len(loaded_ckpt.conversation_history) == 2
    assert loaded_ckpt.conversation_history[0] == "Step 1 complete"


def test_checkpoint_corruption(store):
    """Test 3: Corruption test. Manually store a malformed JSON blob and assert clean failure."""
    agent_id = "agent_m5_3"
    
    # 1. Manually inject a malformed JSON string directly into SQLite
    with sqlite3.connect(store.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO checkpoints (agent_id, checkpoint_data) VALUES (?, ?)", (agent_id, "{bad_json: True"))
        conn.commit()
        
    # 2. Attempt to load and assert it raises CheckpointCorruptError, NOT a fatal JSONDecodeError
    with pytest.raises(CheckpointCorruptError) as exc_info:
        store.load_checkpoint(agent_id)
        
    assert "is corrupt" in str(exc_info.value)
