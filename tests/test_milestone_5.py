import pytest
import sqlite3
import json
from datetime import datetime
from agentos.core.agent import Agent
from agentos.core.task import Task
from agentos.core.state import AgentState
from agentos.core.checkpoint import Checkpoint, CheckpointCorruptError
from agentos.runtime.engine import Runtime
from agentos.runtime.real_agents import multi_step_research_agent_task
from agentos.llm.client import MockLLMClient

def test_save_load_checkpoint(store):
    """Test 1: Save/Load test. Checkpoint a RUNNING agent mid-task, simulate kill, reload."""
    agent_id = "agent_m5_1"
    
    # 1. Create and save a checkpoint
    ckpt = Checkpoint(
        agent_id=agent_id,
        state=AgentState.RUNNING,
        conversation_history=["Step 1 complete", "Step 2 started"],
        task_progress_marker="step_2"
    )
    store.save_checkpoint(ckpt)
    
    # 2. Simulate kill (drop store and recreate)
    del store
    from agentos.storage.sqlite_store import SQLiteStore
    new_store = SQLiteStore(db_path="test_runtime.db")
    
    # 3. Reload and assert
    loaded_ckpt = new_store.load_checkpoint(agent_id)
    assert loaded_ckpt is not None
    assert loaded_ckpt.agent_id == agent_id
    assert loaded_ckpt.state == AgentState.RUNNING
    assert loaded_ckpt.task_progress_marker == "step_2"
    assert len(loaded_ckpt.conversation_history) == 2
    assert loaded_ckpt.conversation_history[0] == "Step 1 complete"

def test_recovery_multi_step_agent(store):
    """Test 2: Recovery test. Crash mid-task and ensure it resumes from the progress marker."""
    runtime = Runtime(store=store)
    client = MockLLMClient()
    agent_id = "agent_m5_2"
    
    task = Task(id="t_m5_2", description="CRASH_MIDWAY test doc", created_time=datetime.now())
    agent = Agent(agent_id=agent_id, task=task)
    agent.transition_to(AgentState.READY)
    store.save_agent(agent)
    
    # 1. Execute the agent for the first time. It is programmed to crash after Step 1.
    runtime.execute(
        agent_id=agent_id,
        agent_callable=lambda: multi_step_research_agent_task(client, store, agent_id, "CRASH_MIDWAY doc"),
        timeout=5
    )
    
    # Verify it actually crashed and saved the step 1 checkpoint
    loaded_agent = store.load_agent(agent_id)
    assert loaded_agent.state == AgentState.FAILED
    
    ckpt = store.load_checkpoint(agent_id)
    assert ckpt.task_progress_marker == "keywords_extracted"
    assert len(ckpt.conversation_history) == 1  # Only Step 1's history
    
    # 2. Execute the agent a second time (Simulate resuming after a crash)
    # We pass "Resumed" in the document so it bypasses the intentional crash logic
    loaded_agent.transition_to(AgentState.READY)
    store.save_agent(loaded_agent)
    
    runtime.execute(
        agent_id=agent_id,
        agent_callable=lambda: multi_step_research_agent_task(client, store, agent_id, "CRASH_MIDWAY doc Resumed"),
        timeout=5
    )
    
    # Verify it completed successfully and appended to the existing checkpoint
    loaded_agent = store.load_agent(agent_id)
    assert loaded_agent.state == AgentState.COMPLETED
    
    final_ckpt = store.load_checkpoint(agent_id)
    assert final_ckpt.task_progress_marker == "completed"
    assert len(final_ckpt.conversation_history) == 2  # Step 1 AND Step 2

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
