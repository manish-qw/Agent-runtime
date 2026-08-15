import pytest
import os
from agentos.runtime.dummy_agents import shutdown_event
from agentos.storage.sqlite_store import SQLiteStore

DB_PATH = "test_runtime.db"

@pytest.fixture
def store():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    store = SQLiteStore(db_path=DB_PATH)
    yield store
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except PermissionError:
            pass

@pytest.fixture(autouse=True)
def cleanup_dummy_agents():
    shutdown_event.clear()
    yield
    shutdown_event.set()
