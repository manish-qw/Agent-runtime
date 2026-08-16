import os
import sys
import time
import signal
import subprocess
import pytest
from agentos.storage.sqlite_store import SQLiteStore
from agentos.core.state import AgentState
from agentos.runtime.engine import Runtime

# Helper script that runs in a subprocess and deliberately hangs during SQLite commit
CRASH_SCRIPT = """
import sqlite3
import time
import sys
from datetime import datetime
from agentos.storage.sqlite_store import SQLiteStore
from agentos.core.checkpoint import Checkpoint
from agentos.core.state import AgentState
from agentos.core.agent import Agent
from agentos.core.task import Task

db_path = sys.argv[1]
store = SQLiteStore(db_path)

# 1. Setup the agent in RUNNING state
task = Task("t_kill", "kill test", datetime.now())
agent = Agent("agent_kill", task)
agent.state = AgentState.RUNNING
store.save_agent(agent)

# 2. Save a valid first checkpoint
cp = Checkpoint("agent_kill", AgentState.RUNNING)
cp.conversation_history = [{"msg": "valid_history_1"}]
store.save_checkpoint(cp)

# 3. Monkeypatch SQLite connection to use a custom connection class that hangs on commit
class DelayedConnection(sqlite3.Connection):
    def commit(self):
        # We only want to hang on the second checkpoint, but for simplicity we can just hang on any commit after the first
        # Wait, the first checkpoint was already saved! So any commit now is the second checkpoint.
        print("ABOUT TO COMMIT SECOND CHECKPOINT", flush=True)
        time.sleep(10)
        super().commit()

def delayed_get_connection(self):
    conn = sqlite3.connect(self.db_path, timeout=10.0, factory=DelayedConnection)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn
    
SQLiteStore._get_connection = delayed_get_connection

# 4. Try to save the second checkpoint (this will hang and get killed)
cp.conversation_history.append({"msg": "valid_history_2"})
store.save_checkpoint(cp)

print("SHOULD NEVER REACH HERE", flush=True)
"""

def test_wal_mid_write_kill_recovery(tmp_path):
    db_path = str(tmp_path / "kill_test.db")
    script_path = str(tmp_path / "crash_script.py")
    
    with open(script_path, "w") as f:
        f.write(CRASH_SCRIPT)
        
    # 1. Spawn the subprocess
    # Use the current python executable so it inherits the .venv
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path.parent.parent) # Root is D:\Placement\AgentOS, wait, better use os.getcwd()
    env["PYTHONPATH"] = os.getcwd()

    proc = subprocess.Popen(
        [sys.executable, script_path, db_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )
    
    # 2. Wait for it to signal that it's hanging inside the commit
    hanging = False
    for line in proc.stdout:
        if "ABOUT TO COMMIT SECOND CHECKPOINT" in line:
            hanging = True
            break
            
    if not hanging:
        print("STDERR:", proc.stderr.read())
        print("STDOUT:", proc.stdout.read())
    assert hanging, f"Subprocess did not reach the commit hang state. STDERR: {proc.stderr.read()}"
    
    # 3. Brutally murder the process mid-commit (kill -9)
    if os.name == 'nt':
        # On Windows, SIGTERM to a subprocess acts like a hard kill (TerminateProcess)
        proc.terminate()
    else:
        os.kill(proc.pid, signal.SIGKILL)
        
    proc.wait(timeout=5)
    
    # 4. Boot the OS Recovery Engine
    store = SQLiteStore(db_path)
    runtime = Runtime(store)
    
    # Prove the agent is currently RUNNING (orphaned by crash)
    agent = store.load_agent("agent_kill")
    assert agent.state == AgentState.RUNNING
    
    # 5. Run the Bootstrap Recovery
    runtime.bootstrap_recovery()
    
    # 6. Verify the results
    # The agent should be READY because it had a valid first checkpoint!
    recovered_agent = store.load_agent("agent_kill")
    assert recovered_agent.state == AgentState.READY
    
    # The checkpoint should NOT be corrupted, and it should NOT contain "valid_history_2"
    # because WAL prevented the torn write from committing.
    checkpoint = store.load_checkpoint("agent_kill")
    assert checkpoint is not None
    assert len(checkpoint.conversation_history) == 1
    assert checkpoint.conversation_history[0]["msg"] == "valid_history_1"

