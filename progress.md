# AgentOS Progress Log

## 2026-08-16 - Production Hardening, SQLite WAL & Bug Fixes

**What changed**:
- Fixed the `PermissionError: [WinError 5] Access is denied` bug on Windows by adding `addopts = --basetemp=tmp_pytest` to `pytest.ini`. This isolated the pytest temporary directory from global file locks caused by crashed database connections.
- Added Jittered Exponential Backoff using the `tenacity` library in `agentos/llm/client.py` and `real_agents.py` to handle API rate limits smoothly.
- Hardened the `google-genai` client initializations by enforcing a 60-second HTTP socket timeout (`http_options=types.HttpOptions(timeout=60000)`) to kill truly hung threads on network level.
- Migrated the Gemini LLM Model to be dynamic. Created a `GEMINI_MODEL="gemini-2.5-flash"` variable in `.env` and loaded it using `load_dotenv(override=True)` to prevent local OS environment variable conflicts.
- Discovered and fixed a critical flaw where Google GenAI SDK was automatically executing tools in the background (`Automatic Function Calling`). Explicitly disabled this using `automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)` to ensure our manual `while True` ReAct loop and crash logic fired correctly.
- Discovered that manually reconstructing `types.FunctionCall` objects stripped hidden `thought_signature` and `id` metadata required by Gemini 2.0+ models, causing `INVALID_ARGUMENT` crashes. Rewrote the Checkpoint conversation history serializer to natively dump and validate Google GenAI `types.Content` objects directly to SQLite JSON using `model_dump(exclude_none=True, mode='json')`. This perfectly preserved all internal metadata.
- Enabled `journal_mode=WAL` and `synchronous=NORMAL` in `SQLiteStore` to fix database locking contention during multi-threaded tests.
- Implemented a two-pass `bootstrap_recovery()` in `Runtime` to automatically load and resume orphaned `RUNNING` agents (from hard kill -9 crashes) and interrupted `FAILED` agents (from soft crashes/timeouts) that have valid checkpoints on system boot.
- Wrote an advanced integration test (`test_kill_recovery.py`) that uses multiprocessing to kill the system with `SIGKILL` (-9) mid-database commit, proving atomic survival.

**Why**:
- The project is claiming to be "production-grade", which means it must survive real-world network hangs, rate limits, file permission errors, SDK behavior changes, and hard power losses. By implementing WAL mode, HTTP timeouts, native JSON serialization for GenAI models, and explicit AFC disabling, the system is now bulletproof under actual API loads and multi-threaded stress.

## 2026-08-16 - True Agents (ReAct) & Tool-Calling Integration

**What changed**:
- Created the `agentos/tools/` directory and built 4 functional tool modules:
  - `math_tools.py` (`add`, `multiply`)
  - `fs_tools.py` (`list_files`, `read_file`, `write_file`)
  - `web_tools.py` (`search_web` using Serper API)
  - `weather_tools.py` (`get_weather` using Weather API)
- Implemented `python-dotenv` explicitly inside `web_tools.py` and `weather_tools.py` to securely load `SERPER_API_KEY` and `WEATHER_API_KEY` from the local `.env` file.
- Created `standalone_agent_test.py` to independently verify the tools using the Gemini SDK's Automatic Function Calling (AFC) capabilities outside of the OS constraints.
- Built `tool_calling_agent_task` in `agentos/runtime/real_agents.py`. This is a "True Agent" that executes a manual ReAct (Reason + Act) loop. It dynamically parses LLM function calls, executes the Python tools locally, and most importantly, takes a SQLite `Checkpoint` snapshot *after every single tool call*.
- Implemented a temporary simulated crash mechanism to forcefully halt the agent after its first tool call, proving the OS can capture mid-loop state.
- Rewrote `main.py` to orchestrate 3 distinct True Agents (Math, FileSystem, and Real-World Web/Weather) sequentially through a 3-phase execution lifecycle:
  1. **Execution**: Running the agents until they hit the simulated crash, landing them in a `FAILED` state.
  2. **Recovery**: Fetching crashed agents from the database and transitioning them back to `READY`.
  3. **Resumption**: Re-executing the agents, allowing them to load their checkpoint, skip the first tool call, and seamlessly finish the rest of the task.

**Why**:
- By combining the resilient `checkpoints` table with manual ReAct tool-calling loops, we solved the biggest problem with LLM agents: fragility. A long-running agent that makes 10 API calls can now crash on the 9th call, and AgentOS can resume it without re-running the first 8 calls. This drastically saves API credits and wall-clock time, proving the system is robust enough for real-world production loads.

## 2026-08-15 - Milestone 5 Implementation

**What changed**:
- Added `checkpoints` table to `SQLiteStore` and methods to `save_checkpoint` and `load_checkpoint`.
- Created `Checkpoint` dataclass to encapsulate agent state, timestamp, conversation history, and progress markers.
- Built a `multi_step_research_agent_task` that extracts keywords (Step 1) and generates a summary (Step 2), persisting its progress to the database between steps.
- Modified the Core `Agent` state machine to allow `FAILED -> READY` transitions so crashed agents can be legally resumed.
- Implemented and passed tests verifying save/load functionality, mid-task recovery after simulated crashes, and safe error handling for corrupted SQLite checkpoint blobs.

**Why**:
- This addresses a fundamental flaw in basic LLM agent pipelines: cost and latency. If a multi-step agent crashes at step 50 out of 51, restarting from step 1 burns massive amounts of tokens and wall-clock time. Checkpointing ensures we can safely resume exactly where we left off, proving our OS architecture scales to long-running asynchronous tasks.

## 2026-08-15 - Milestone 4 Implementation

**What changed**:
- Built an `LLMClient` interface (`agentos/llm/client.py`) with two implementations: `MockLLMClient` for fast, free, and deterministic unit testing, and `GeminiLLMClient` for real API calls using the `google-genai` SDK and Gemini 2.5 Flash Lite.
- Implemented real agent workloads (`research_agent_task` and `coding_agent_task`) in `agentos/runtime/real_agents.py`.
- Upgraded the `Runtime.execute` engine to detect when an agent returns a token count, automatically parsing the tuple `(result, tokens_used)` and appending the usage to the agent's PCB state (`token_usage`).
- Wrote robust, mocked unit tests in `tests/test_milestone_4.py` to verify the execution and token capture plumbing without spending API credits.
- Created `tests/integration/test_real_llm.py` which actually hits the Gemini API, automatically skipping if no API key is found.
- Cleaned up the test suite by extracting the SQLite `store` database setup into a global `conftest.py` fixture, implementing best practices for database test isolation and teardown cleanup events.

**Why**:
- This milestone proves the foundational layers of our OS (PCB, Runtime, Scheduler) actually work with real LLMs. By abstracting the LLM behind an interface, we guarantee deterministic testing—a core architectural goal. Wiring the extracted token counts directly into the database PCB brings our `TokenAwareScheduler` from Milestone 3 to life.

## 2026-08-14 - Milestone 3 Implementation

**What changed**:
- Added `BaseScheduler` interface and implemented `FIFOScheduler`, `PriorityScheduler` (using `heapq`), and `RoundRobinScheduler` in `agentos/scheduler/`.
- Adapted the `RoundRobinScheduler` to use cooperative yielding. Agents explicitly return `"YIELD"` when their "time slice" (e.g. an atomic LLM tool call step) is over.
- Implemented the advanced `TokenAwareScheduler` which utilizes priority-queuing but defers execution if dispatching the agent would exceed a predefined `MAX_BUDGET` of tokens-in-flight.
- Updated the `Runtime` execution engine to handle `"YIELD"` results by safely placing the agent back in `READY` status, instead of marking it `COMPLETED`.
- Wrote and passed comprehensive tests (`tests/test_milestone_3.py`) verifying exact scheduling order, budget constraint handling, and multi-thread stress testing of the scheduler queues (100 concurrent submissions).

**Why**:
- This elevates the runtime into a true OS-style scheduler capable of managing hundreds of agents. By adding cooperative yielding and a token-budget scheduler, we addressed the real-world bottlenecks of LLM pipelines (API costs and rate limits) rather than falsely equating CPU cycles with agent execution time.

## 2026-08-14 - Milestone 2 Implementation

**What changed**:
- Added `agentos/runtime/dummy_agents.py` with mock callables (`sleep_agent`, `exception_agent`, `sleep_forever_agent`) to test the runtime engine's handling of various states.
- Created `agentos/runtime/engine.py` with a `Runtime` class.
- Implemented `Runtime.execute()` using a robust `concurrent.futures.ThreadPoolExecutor` concurrency model.
- Added strict timeout handling using `future.result(timeout=X)` to prevent hung agents from blocking the runtime.
- Added complete exception isolation to ensure crashing agents cleanly transition to `FAILED` state and log their error trace without impacting the overarching process.
- Wrote tests (`tests/test_milestone_2.py`) to prove the runtime correctly processes successful completions, crash isolations, and infinite-loop timeouts.

**Why**:
- This fulfills the critical requirement of agent execution in an OS-like environment. An operating system cannot allow a user process to crash the kernel or run infinitely. By using a ThreadPoolExecutor with explicit timeouts and try/catch boundaries, we guarantee that the `Runtime` correctly updates PCB state regardless of how badly a dummy agent misbehaves.


## 2026-08-13 - Milestone 1 Implementation

**What changed**:
- Added PCB (Process Control Block) fields to the `Agent` class (`created_time`, `execution_history`, `token_usage`, `checkpoint_location`).
- Set up a Python Virtual Environment (`.venv`) and a `requirements.txt` containing `pytest`.
- Created the SQLite storage layer (`SQLiteStore`) in `agentos/storage/sqlite_store.py` to persist `Agent` processes.
- Wrote and passed tests for PCB persistence, state updates across loads, and database failure recovery.

**Why**:
- Creating a persistent PCB gives agents an identity that survives beyond single process execution. Moving from purely memory-bound agents to a database-backed execution allows us to implement our OS scheduling architecture later on. This also isolates tests safely in `.venv`.

## 2026-08-13 - Milestone 0 Implementation

**What changed**:
- Created the project skeleton (`core/`, `scheduler/`, `runtime/`, `storage/`, `tests/`).
- Added `.gitignore` to prevent tracking cache and this progress file.
- Defined `AgentState` enum to manage agent states (CREATED, READY, RUNNING, BLOCKED, COMPLETED, FAILED).
- Created `Task` dataclass to hold task metadata.
- Implemented `Agent` class that enforces valid state transitions and manages state effectively.
- Added and passed `pytest` tests validating creation, state transitions, and state isolation across multiple agents.

**Why**:
- This sets the foundational architecture for `AgentOS` as outlined in the project plan. The OS-inspired runtime requires these core objects before any LLM integration or scheduling logic can be safely built and managed. The state machine validation is crucial for preventing unexpected runtime behavior down the line.

 
 