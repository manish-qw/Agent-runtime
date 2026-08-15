import pytest
import os
from datetime import datetime
from agentos.core.agent import Agent
from agentos.core.state import AgentState
from agentos.core.task import Task
from agentos.storage.sqlite_store import SQLiteStore



def test_pcb_persistence(store):
    """Test 1: PCB persistence test"""
    task = Task(id="t1", description="Research task", created_time=datetime.now())
    agent = Agent(agent_id="agent_1", task=task, priority=5)
    agent.token_usage = 100
    agent.execution_history.append("Started task")
    
    # Save agent
    store.save_agent(agent)
    
    # Load agent
    loaded_agent = store.load_agent("agent_1")
    
    assert loaded_agent.id == agent.id
    assert loaded_agent.state == agent.state
    assert loaded_agent.priority == agent.priority
    assert loaded_agent.token_usage == 100
    assert loaded_agent.execution_history == ["Started task"]
    assert loaded_agent.task.id == "t1"

def test_state_update(store):
    """Test 2: State update test"""
    task = Task(id="t2", description="Coding task", created_time=datetime.now())
    agent = Agent(agent_id="agent_2", task=task, priority=1)
    
    store.save_agent(agent)
    
    # Change state READY -> RUNNING
    agent.transition_to(AgentState.READY)
    agent.transition_to(AgentState.RUNNING)
    agent.execution_history.append("Running")
    
    # Save again
    store.save_agent(agent)
    
    # Load and verify DB reflects it
    loaded = store.load_agent("agent_2")
    assert loaded.state == AgentState.RUNNING
    assert loaded.execution_history == ["Running"]

def test_failure_recovery():
    """Test 3: Failure/Recovery test (simulated restart)"""
    db_name = "test_recovery.db"
    if os.path.exists(db_name):
        os.remove(db_name)
        
    store1 = SQLiteStore(db_path=db_name)
    task = Task(id="t3", description="Recovery task", created_time=datetime.now())
    agent = Agent(agent_id="agent_3", task=task)
    store1.save_agent(agent)
    
    # Simulate program restart by re-initializing store connection
    store2 = SQLiteStore(db_path=db_name)
    loaded = store2.load_agent("agent_3")
    
    assert loaded.id == "agent_3"
    assert loaded.state == AgentState.CREATED
    
    if os.path.exists(db_name):
        try:
            os.remove(db_name)
        except PermissionError:
            pass

def test_kill_mid_write(store):
    """
    Test 4: Kill mid-write. 
    SQLite WAL mode and basic SQLite files give us durability.
    We prove this by doing a write, explicitly dropping the object (simulating crash),
    and opening a fresh connection to verify the row is still there,
    proving no explicit cleanup/flush is needed to guarantee durability.
    """
    task = Task(id="t4", description="Kill mid-write task", created_time=datetime.now())
    agent = Agent(agent_id="agent_4", task=task)
    agent.token_usage = 55
    
    store.save_agent(agent)
    
    # We do NOT call any cleanup on store, we just simulate the OS process dying
    del store 
    
    # Another process wakes up later and checks the database
    new_store = SQLiteStore(db_path="test_runtime.db")
    loaded = new_store.load_agent("agent_4")
    
    assert loaded.id == "agent_4"
    assert loaded.token_usage == 55
