# ⚠️ STRICT AGENT INSTRUCTIONS
**Build the project ONLY when the user explicitly asks.** Do not blindly implement this entire project or jump ahead. This document is strictly for reference. Wait for the user to specify which milestone or feature to work on, ask for clarification if needed, and do exactly what the user requests step-by-step.

---

# AgentOS — Detailed Milestone Plan
*Calibrated for: a strong placement-season project, not a research paper or a product.*

## How the bar is set in this document

For every milestone you'll see three sections:

- **Core (build this)** — the part that must exist and must be solid. This is what you demo and what you should be able to defend line-by-line in an interview.
- **Why this bar** — the one or two sentences that justify why we stop here and don't go further. This doubles as your interview answer when someone asks "why didn't you do X."
- **Optional (mention, don't over-invest)** — real extensions that show you understand the next layer of the problem. You say "I designed for this, and partially implemented / could extend to this" — you do NOT need working code for most of these unless you have spare time.

A good rule while building: if a feature takes more than ~20% extra effort for a "nice to have that's hard to explain in 2 sentences," it's optional-tier, not core-tier. Interviewers reward depth-with-clarity over breadth-with-vagueness.

---

## Milestone 0 — Project Foundation

### Core (build this)
- `Agent`, `Task`, `AgentState` exactly as scoped in the reference doc — plain Python classes/dataclasses, no DB, no async yet.
- State machine enforced as actual code, not just a comment. A `transition(new_state)` method that raises on illegal transitions (e.g., `COMPLETED -> RUNNING`). This is the single most important thing in this milestone — it's what makes the "OS" framing credible instead of decorative.
- Unit tests: Test 1, 2, 3 from the reference doc, using `pytest`.
- Clean package structure exactly as laid out (`core/`, `scheduler/`, `storage/`, `runtime/`, `tests/`) even though most folders are empty right now — this signals you planned the architecture up front, which is a good interview talking point ("I designed the folder structure around OS subsystems before writing any agent logic").

### Why this bar
This milestone has zero AI in it on purpose. Its only job is to prove the state machine is real and enforced, not just documented. Going deeper here (e.g., building a generic FSM library) is solving a problem you don't have yet.

### Optional (mention, don't over-invest)
- A `TransitionError` with a readable message showing the invalid transition — cheap to add, makes the demo look polished.
- A `state_history` list on `Agent` (list of `(state, timestamp)` tuples) — this becomes very useful later for Milestone 5 (checkpointing) and gives you something concrete to show when asked "how do you debug an agent."

### Interview line for this milestone
*"I started with just the state machine, because if agent lifecycle transitions aren't enforced correctly, everything built on top of it — scheduling, checkpointing — inherits that bug silently."*

---

## Milestone 1 — Agent Process Control Block (PCB)

### Core (build this)
- SQLite (not Postgres — see below) table `agents`: `id, state, priority, created_at, metadata (JSON text), tokens_used`.
- A thin `AgentStore` class with `save(agent)`, `load(agent_id)`, `update_state(agent_id, new_state)` — this is your DAO layer, keep it small and explicit, don't reach for an ORM.
- Persistence tests: create → save → simulate restart (new Python process or just a fresh `AgentStore` instance pointed at the same DB file) → load → assert state matches.
- A "kill mid-write" test: this doesn't need to be fancy — write, then in the test intentionally don't call any cleanup, open a second connection, and confirm the row is still there. SQLite's durability gives you this almost for free; the point is *you tested for it*, not that you built durability yourself.

### Why this bar
Postgres, connection pooling, migrations — all of that is infrastructure weight with no payoff at this project's scale. SQLite in WAL mode gives you real durability guarantees for a single-writer system, and you can say that sentence in an interview and it's *true*, not a dodge. The goal of this milestone is "state survives a restart," not "this scales to 10,000 concurrent writers."

### Optional (mention, don't over-invest)
- Enabling `PRAGMA journal_mode=WAL` explicitly and explaining why (better concurrent read behavior, crash-safe) — this is a 1-line change that gives you a genuinely good technical detail to drop in an interview.
- A `metadata` JSON column that stores flexible per-agent-type data instead of rigid columns — worth doing since it's low effort and shows schema-design judgement (you avoided premature normalization).
- Swappable storage backend (an abstract `StorageBackend` interface with SQLite as the only real implementation) — mention "I designed the store behind an interface so Postgres could be swapped in without touching the runtime," but don't actually build a Postgres implementation unless you have time to spare. Half-built Postgres support is worse than honestly-scoped SQLite.

### Interview line for this milestone
*"I used SQLite deliberately, not because I didn't know Postgres — because this system has one writer process, and SQLite's WAL mode already gives crash-safe durability at that scale. Reaching for Postgres here would've been solving a scaling problem I don't have."*

---

## Milestone 2 — Agent Runtime

### Core (build this)
- A `Runtime` class with a single method like `execute(agent) -> Result`. It updates state before/after (`READY -> RUNNING -> COMPLETED/FAILED`), and every state change goes through the PCB from Milestone 1 — this is where M0/M1/M2 actually connect, which is worth calling out explicitly in your writeup.
- Dummy agents: a `sleep(n)` agent, a `raise_exception()` agent, a `sleep_forever()` agent — implemented as simple callables or a tiny `DummyAgentTask` class, not anything elaborate.
- **Timeout handling done properly**: use `concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=...)`, or `asyncio.wait_for` if you go async — either is fine, but pick one and understand *why* a bare `signal.alarm` wouldn't work well here (doesn't work well on non-main threads / Windows). This single detail — correctly handling a hung task — is a strong interview differentiator; most student projects get this wrong or skip it.
- Exception isolation: a crashing agent must not crash the runtime loop. Wrap execution in try/except, catch the exception, transition to `FAILED`, store the error message in PCB metadata, move on.
- Tests: run 10 dummy agents to completion, one exception-raising agent ends in `FAILED` without crashing the process, one `sleep_forever` agent gets killed by timeout and ends in `FAILED`.

### Why this bar
This is genuinely one of the most interview-worthy milestones because "how do you prevent one bad task from taking down the whole system" is a real systems question, and you'll have a real, correct answer instead of a hand-wave. Going further (process-level isolation via subprocess/containers) is a legitimate next step but is real infra work, not a weekend addition.

### Optional (mention, don't over-invest)
- Running each agent in a subprocess instead of a thread, for true kill-on-timeout instead of "abandon the thread and hope." Worth *mentioning as the more correct approach* even if you implement threads — "threads can't be forcibly killed in Python, so a hung agent's thread leaks until process exit; subprocess-based isolation would fix that, but wasn't worth the complexity for this project's scale."
- A retry policy (`max_retries`, backoff) on `FAILED` — cheap to add, nice to show.

### Interview line for this milestone
*"The hard part isn't running an agent, it's making sure a single hung or crashing agent can't take the whole runtime down. I used a thread pool with an explicit timeout, and every execution is wrapped so a failure updates state to FAILED rather than propagating."*

---

## Milestone 3 — Scheduler

### Core (build this)
- A `Scheduler` interface: `submit(agent)`, `get_next()`, `update(agent)`.
- **FIFO** and **Priority** scheduling implemented properly (a real heap/priority queue via `heapq`, not a sorted list you re-sort every time — mention the complexity difference, O(log n) vs O(n log n), it's a cheap correctness/CS-fundamentals point).
- Round Robin: implement it, but keep the time-slice concept honest — for LLM calls a "time slice" doesn't mean CPU cycles, it means something like "one tool-call step" or "N seconds of wall time before yielding." Decide which definition you're using and say so explicitly; this is exactly the kind of detail that separates "copied the OS algorithm" from "adapted it to agents."
- Concurrency test: submit 20 agents, run with a thread pool, assert no agent is executed twice and none are lost — use a simple counter/set with a lock, or just check final states cover all 20 exactly once.
- Stress test: 100 agents submitted, verify queue drains correctly and no agent silently disappears.

### Why this bar — and the key judgement call
This is the milestone with the biggest "toy vs real" gap. Implementing textbook FIFO/Priority/Round-Robin with dummy agents is what everyone does; it's fine as your **required baseline**, and you should be completely honest about it in interviews as your "correctness layer."

**One upgrade is worth doing here and pushes this from good to strong:** a **token/rate-budget-aware scheduler mode** — e.g., the scheduler tracks estimated tokens-in-flight and defers `get_next()` (or reorders) when a budget threshold would be exceeded. This doesn't require a real LLM yet (Milestone 4) — you can fake token cost as a fixed or random number per dummy agent. This is the one piece of "real agent scheduling" logic that a textbook OS course never covers, and it's genuinely not hard to build given you already have priority queue and PCB (tokens field) infrastructure. I'd rate this as **recommended, not strictly required** — do it if Milestone 3 goes smoothly, skip it if you're behind schedule and just describe it as future work.

### Optional (mention, don't over-invest)
- Token/rate-budget-aware scheduling (see above) — recommended optional, higher value than the other optionals here.
- Multi-level feedback queue (agents that keep timing out get demoted in priority) — good to *mention* as "the natural next step from Round Robin," not worth implementing.
- Fair-share scheduling across "agent types" — skip entirely, this is scope creep for this project.

### Interview line for this milestone
*"I implemented the three classical algorithms as a correctness baseline, but the interesting adaptation was priority scheduling constrained by a token budget — because in LLM systems the real bottleneck usually isn't CPU time, it's rate limits and cost, which classical OS scheduling doesn't model at all."*

---

## Milestone 4 — Real LLM Agents

### Core (build this)
- Wire the Anthropic API (or OpenAI, whichever you have access/credits for) behind a small `LLMClient` interface, so it can be mocked in tests — this interface is what makes "deterministic testing" from the reference doc actually possible.
- Two agent types exactly as scoped: **Research Agent** (doc → summary) and **Coding Agent** (question → solution). Keep the prompts simple; this milestone is about the plumbing, not prompt engineering.
- Token usage captured from the real API response and written into the PCB (`tokens_used` field from Milestone 1) — this is the moment M1's PCB design actually pays off, good to call out.
- Mocked-LLM unit tests (fast, no real API calls, no cost) plus a small number of real-integration tests (5 agents, real API, checked into a "run manually / not in CI" bucket) — be explicit about this split, it shows testing maturity.

### Why this bar
Two agent types is enough to prove the runtime is agent-type-agnostic; building five agent types multiplies effort without teaching the system anything new. Real cost/rate-limit handling is legitimately hard and belongs in Milestone 6 as an experiment, not baked in half-done here.

### Optional (mention, don't over-invest)
- Basic retry-with-backoff specifically for API rate-limit errors (429s) — worth doing if time allows, it's a small addition and a very "I've used a real LLM API in production" signal.
- Streaming responses — skip; adds real complexity (partial-state handling) for no payoff at this project's scale, and it's fine to say so.

### Interview line for this milestone
*"I kept it to two agent types deliberately, because the goal of this milestone was proving the runtime and scheduler are agnostic to what the agent actually does — the interesting engineering was already done in Milestones 2 and 3."*

---

## Milestone 5 — Context Checkpointing

### Core (build this)
- `Checkpoint` object: agent ID, state, conversation history (list of messages), task progress marker, timestamp — store as a JSON blob in a `checkpoints` table (new table, same SQLite DB), not a new subsystem.
- Save/Load test: checkpoint a `RUNNING` agent mid-task, simulate a kill (just stop calling anything further in the test), reload from the checkpoint, assert state and history match.
- Recovery test: an agent that's partway through a multi-step task (e.g., Research Agent has read the doc but hasn't summarized yet) — checkpoint, "crash," restore, and it resumes from the progress marker instead of restarting the whole task. This is the real test of whether checkpointing is doing anything — a checkpoint that only proves the *ORM roundtrips correctly* isn't proving resumability.
- Corruption test: manually store a malformed/truncated JSON blob, attempt load, assert it fails cleanly (raises a specific `CheckpointCorruptError` or similar) rather than crashing the whole process.

### Why this bar
Full crash-consistency across arbitrary points in a tool call (i.e., "what if the agent crashed *during* a tool execution, was the tool's side effect already applied?") is a real distributed-systems problem — idempotency, at-least-once vs exactly-once — and solving it properly is a research-adjacent rabbit hole. For this project, checkpointing *between* discrete task steps (not mid-tool-call) is the right, honest scope.

### Optional (mention, don't over-invest)
- Checkpointing at tool-call boundaries specifically (before/after each tool invocation, not just at coarse task-progress markers) — mention this as "the granularity I'd increase for a production system," don't build it.
- Idempotency keys for tool calls so a resumed agent doesn't double-execute a side-effecting action — good one-liner to drop as "the next problem this surfaces," genuinely the kind of thing that shows systems maturity in an interview even unimplemented.

### Interview line for this milestone
*"Checkpointing happens at task-progress boundaries, not mid-tool-call — going finer-grained runs into idempotency problems, like 'what if the tool call succeeded but the checkpoint wasn't saved yet,' which is a real distributed systems problem I scoped out of this project deliberately rather than half-solving."*

---

## Milestone 6 — Benchmark Framework

### Core (build this)
- Workload generator: produce N agents (10/50/100) with short/medium/long dummy tasks (vary `sleep()` duration or number of steps — doesn't need real LLM calls for most runs, keep this cheap to re-run).
- Baseline comparison: `asyncio.gather` (or thread pool, no scheduler) vs AgentOS (scheduler-controlled) — same workload, same environment, measured back to back.
- Metrics actually captured, not eyeballed: total completion time, throughput (agents/sec), failure count, and — if you did the optional token-budget scheduler in M3 — tokens consumed and rate-limit-error count as a differentiator.
- Repeatability test: same workload, 3 runs, report mean/variance — this alone (having variance instead of a single number) is a noticeably above-average thing to show and takes very little extra code.

### Why this bar
A benchmark that reports one number from one run ("it took 12 seconds") is not defensible under a follow-up question. A benchmark with 3 runs and a clear baseline-vs-AgentOS comparison, with one findable, explainable result, is exactly the level this project needs — you don't need statistical rigor beyond mean/variance.

### Optional (mention, don't over-invest)
- Load test at 100 real-LLM agents — expensive and rate-limit-fragile, fine to run once for a screenshot, not worth building infrastructure around.
- Plots (matplotlib bar chart of completion time by scheduling algorithm) — cheap, visually strong for a README/demo, worth doing if you have 30 minutes spare.

### Interview line for this milestone
*"The benchmark's whole point was having one specific, defensible claim — for example, that priority scheduling under a token budget reduced P95 completion time versus naive concurrent execution, measured over three runs. I intentionally didn't try to build a general-purpose benchmarking framework; that's a different project."*

---

## Overall "good project" bar — one paragraph you can reuse

*"AgentOS borrows OS abstractions — process control blocks, scheduling, checkpointing — and applies them to managing autonomous LLM agents. I built it in six milestones, each with its own tests, deliberately keeping scope tight: SQLite over Postgres, thread-based over process-based isolation, task-boundary checkpointing over tool-call-level checkpointing. The one place I went beyond a textbook implementation was the scheduler, where I added a token-budget-aware priority mode, because rate limits and cost — not CPU time — are the actual bottleneck in agent systems."*

That paragraph, if true of what you built, is a strong 45-second interview answer on its own.

---

## Suggested build order given your constraint (good project, not endless scope)

1. M0 → M1 → M2: build fully, don't skip tests. This is your foundation and it's cheap.
2. M3: build FIFO + Priority + Round Robin fully. Attempt the token-budget mode *only if M0-M2 didn't overrun your time budget*.
3. M4: two agent types, mocked tests + a handful of real API calls. Don't scale up agent types.
4. M5: task-boundary checkpointing, all four tests. Skip tool-call-level granularity.
5. M6: baseline vs AgentOS, 3 repeated runs, one clear finding. Add a chart if time allows.

If you're short on time before placements, M0-M4 with solid tests is already a demonstrable, defensible project. M5-M6 are what push it from "good" to "strong," so protect time for at least M5.
