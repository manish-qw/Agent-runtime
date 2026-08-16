import pytest
import os
from agentos.runtime.dummy_agents import shutdown_event
from agentos.storage.sqlite_store import SQLiteStore

DB_PATH = "test_runtime.db"

@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_runtime.db")
    store = SQLiteStore(db_path=db_path)
    yield store

@pytest.fixture(autouse=True)
def cleanup_dummy_agents():
    shutdown_event.clear()
    yield
    shutdown_event.set()
