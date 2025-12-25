# JQM Implementation Notes

This document captures **design decisions**, **problems encountered**, **how they were solved**, and **most importantly, WHY they were solved that way**.

## Table of Contents
1. [Core Design Decisions](#core-design-decisions)
2. [Problems and Solutions](#problems-and-solutions)
3. [Architectural Patterns](#architectural-patterns)
4. [Testing Strategies](#testing-strategies)

---

## Core Design Decisions

### 1. TCP/JSON Protocol with Length Prefix

**Decision**: Use 8-byte big-endian length prefix before JSON payload.

**Why**:
- **Problem**: TCP is stream-based, not message-based. Receiver doesn't know where one message ends and next begins.
- **Alternative considered**: Newline-delimited JSON (NDJSON)
- **Why not NDJSON**: JSON payloads themselves might contain newlines in strings, would require escaping
- **Why length prefix**: Clean message framing, no escaping needed, efficient binary parsing
- **Why 8 bytes**: Supports messages up to ~18 exabytes (way more than needed), consistent size simplifies parsing
- **Why big-endian**: Network byte order standard (though choice doesn't matter as long as it's consistent)

**Location**: `jqm/common/protocol.py`

```python
def send_message(sock: socket.socket, message: dict[str, Any]) -> None:
    json_bytes = json.dumps(message).encode(MESSAGE_ENCODING)
    length = len(json_bytes)
    length_prefix = length.to_bytes(MESSAGE_LENGTH_PREFIX_SIZE, byteorder="big")
    sock.sendall(length_prefix + json_bytes)
```

### 2. Threading vs Async

**Decision**: Use threading with `threading.Thread` and `threading.Lock`.

**Why**:
- **Constraint**: No third-party packages allowed (no `asyncio` libraries like `aiohttp`)
- **Standard library async**: Would require rewriting all socket code for `asyncio`
- **Simplicity**: Threads are simpler to reason about for this use case
- **Blocking I/O is fine**: Job execution is inherently blocking (waiting for subprocess)
- **Scale**: We don't need to handle thousands of connections, just a few CLI/HTTP clients
- **Thread-per-client**: Simple model, adequate for our needs

**Trade-off accepted**: Higher memory overhead per connection vs complexity of async code.

### 3. Thread Safety with Lock

**Decision**: Wrap ALL JobQueue public methods with `with self._lock:`.

**Why**:
- **Concurrent access**: JobQueue is accessed from:
  - Multiple TCP client threads (handling different connections)
  - JobExecutor background thread (executing jobs)
- **Race conditions**: Without locking, could corrupt job list, miss state changes, return inconsistent data
- **Example race**: Client deletes job while executor is iterating jobs → crash
- **Why not fine-grained locking**: Queue operations are fast, one lock is simpler and safer
- **Internal helpers**: `_unlocked` methods for use within already-locked context (avoid deadlock)

**Location**: `jqm/engine/queue.py:55`

```python
def __init__(self):
    self._lock = threading.Lock()

def add_job(self, command: str, args: list[str], cwd: str) -> int:
    with self._lock:  # Acquire lock for entire operation
        job_id = self._next_job_id
        self._next_job_id += 1
        # ... safe to modify shared state
```

### 4. Job State vs to_skip Flag

**Decision**: `state` is volatile (changes during execution), `to_skip` is persistent flag.

**Why**:
- **Different lifecycles**:
  - `to_skip` = user's intent ("I want to skip this job")
  - `state` = current execution state ("job is currently running")
- **State transitions**: `pending → running → completed/failed` but `to_skip` stays constant
- **Skip state**: When `to_skip=True`, job's state is `skip` and it won't be executed
- **Toggle behavior**: User can toggle `to_skip`, which changes state between `pending ↔ skip`
- **Why not just state**: Once job completes, would lose information about whether it was skipped vs succeeded

**Location**: `jqm/engine/job.py:27-30`

### 5. UTC Timestamps Only

**Decision**: All timestamps use `datetime.now(timezone.utc).isoformat()`.

**Why**:
- **Problem**: `datetime.now()` without timezone is "naive" - ambiguous during DST transitions
- **Example issue**: Job started at "2:30 AM" - which 2:30 AM during fall DST switch?
- **Why UTC**: Unambiguous, no DST, industry standard for distributed systems
- **ISO format**: String format is portable, human-readable, sortable
- **Why not Unix timestamp**: Less human-readable in logs, ISO format is standard for JSON APIs

**Location**: `jqm/engine/job.py:66, 75`

```python
from datetime import datetime, timezone

def start(self) -> None:
    self.started_at = datetime.now(timezone.utc).isoformat()
```

### 6. Event Broadcasting from Executor, Not Dispatcher

**Decision**: Events are broadcast from `JobExecutor`, not from `CommandDispatcher`.

**Why**:
- **Separation of concerns**:
  - Dispatcher = handles commands from clients
  - Executor = performs actual work (execution)
- **Who knows best**: Executor knows exact moment job starts/completes (subprocess lifecycle)
- **Accurate timestamps**: Executor broadcasts with actual execution timestamps
- **Example**: `add_job` command doesn't broadcast `job_status_changed` because adding ≠ starting
- **Queue state changes**: Dispatcher broadcasts those because user commands change queue state

**Location**: `jqm/engine/executor.py:136-152, 206-211`

---

## Problems and Solutions

### Problem 1: JSON Encoding Exception Type

**What happened**: Used `json.JSONEncodeError` in except clause, got `AttributeError`.

**Root cause**: `json.dumps()` raises `TypeError` for unserializable objects, not `JSONEncodeError`.

**How fixed**: Changed `except json.JSONEncodeError` to `except TypeError`.

**Why this fix**:
- `JSONEncodeError` is for decoding (parsing), not encoding
- Python's json module raises `TypeError` when it can't serialize an object
- Catching correct exception ensures error handling actually works

**Lesson learned**: Always verify what exceptions a function actually raises, don't assume!

**Location**: `jqm/common/protocol.py:26` (Fixed in commit c6cd2d2)

### Problem 2: Mock Socket recv() Exhaustion

**What happened**: Test failed with `StopIteration` from mock `recv()`.

**Root cause**: Mock's `side_effect` list was exhausted when test called `recv()` more times than expected.

**How fixed**: Properly calculated chunk sizes and created correct side_effect list.

**Why this fix**:
- Mock `side_effect` iterator stops when exhausted
- Need to simulate chunked TCP reads (might receive partial message)
- Test should provide exact sequence of chunks receiver will get

**Example**:
```python
# Message: 8-byte length + JSON
# Simulate receiving in 2 chunks
mock_recv.side_effect = [
    length_prefix[:4],  # First 4 bytes
    length_prefix[4:] + json_bytes,  # Rest of length + JSON
]
```

**Lesson learned**: When mocking stateful APIs like sockets, simulate realistic behavior (chunked reads).

**Location**: `tests/test_protocol.py` (Fixed in commit c6cd2d2)

### Problem 3: Mutable Data Exposure

**What happened**: `Job.to_dict()` returned reference to internal `self.args` list.

**Risk**: External code could modify returned dict and corrupt job's internal state.

**How fixed**: Return `self.args.copy()` instead of `self.args`.

**Why this fix**:
- **Encapsulation**: Internal state should not be modifiable from outside
- **Defensive copying**: Prevent accidental bugs from client code
- **Example attack**:
  ```python
  job_dict = job.to_dict()
  job_dict["args"].append("--malicious")  # Would modify job.args!
  ```
- **Cost**: Small - copying a list of strings is cheap, safety is worth it

**Test added**: `test_to_dict_returns_copy_of_args()` verifies modification doesn't affect original.

**Lesson learned**: Always return copies of mutable internal data structures.

**Location**: `jqm/engine/job.py:81` (Fixed in commit c65f9bb)

### Problem 4: Integration Test State Pollution

**What happened**: Tests failed when run together but passed individually.

**Root cause**: Tests shared same EngineServer instance, job IDs incremented across tests.

**How fixed**: Added `setUp()` method that:
1. Resets queue state to `stopped`
2. Deletes all non-running jobs before each test

**Why this fix**:
- **Test isolation**: Each test should start with clean state
- **Idempotent**: Tests can run in any order
- **Why not recreate server**: Server is expensive to start/stop (threads, sockets), cleanup is faster
- **Why delete in setUp not tearDown**: setUp guarantees clean state even if previous test crashed

**Location**: `tests/test_engine_server.py:33-50` (Fixed in commit 91f7747)

```python
def setUp(self):
    """Set up test client for each test."""
    self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.client.connect(("127.0.0.1", self.port))

    # Reset queue state to stopped
    send_message(self.client, {"cmd": "set_queue_state", "state": "stopped"})
    receive_message(self.client)

    # Clear the queue for each test
    send_message(self.client, {"cmd": "list_jobs"})
    list_response = receive_message(self.client)

    for job in list_response["data"]["jobs"]:
        if job["state"] != "running":
            send_message(self.client, {"cmd": "delete_job", "job_id": job["id"]})
            receive_message(self.client)
```

### Problem 5: Resource Warning - Unclosed File

**What happened**: Test passed but Python warned about unclosed file from subprocess.

**Root cause**: `subprocess.Popen` with `stdout=PIPE` creates a file object that must be explicitly closed.

**How fixed**: Added `try/finally` block to ensure `process.stdout.close()` always runs.

**Why this fix**:
- **Resource leak**: Unclosed files consume file descriptors (limited resource)
- **Why finally**: Guarantees cleanup even if exception occurs during processing
- **Why not with statement**: Popen doesn't support context manager for stdout specifically
- **Impact**: Without fix, running many jobs could exhaust file descriptors

**Location**: `jqm/engine/executor.py:174-185` (Fixed in commit 7a3da8c)

```python
try:
    process = subprocess.Popen(...)
    try:
        if process.stdout:
            for line in process.stdout:
                log_file.write(line)
        exit_code = process.wait()
    finally:
        # Ensure stdout is closed even if error occurs
        if process.stdout:
            process.stdout.close()
except FileNotFoundError as e:
    # ...
```

### Problem 6: Log Footer Missing Timestamp

**What happened**: Log footer showed `ended_at: None` because `job.complete()` was called inside file context.

**Root cause**:
1. File was opened for writing
2. Called `job.complete(exit_code)` inside the `with` block
3. Tried to write footer with `job.ended_at`
4. But `job.ended_at` is set by `complete()` which hadn't executed yet due to file buffering

**Actually, different issue**: Called `job.complete()` inside `with` block, then tried to write footer. But needed to get `job.ended_at` which is set by `complete()`.

**Real root cause**: The code structure made `ended_at` unavailable when writing footer.

**How fixed**:
1. Call `job.complete(exit_code)` OUTSIDE the first file context
2. Open file again with `"a"` (append) to write footer
3. Now `job.ended_at` is available

**Why this fix**:
- **Sequencing**: Must complete job first to get `ended_at` timestamp
- **Two file operations**: First write header+output, then write footer separately
- **Why append mode**: Ensures footer goes at end without overwriting

**Location**: `jqm/engine/executor.py:198-204` (Fixed in commit 7a3da8c)

```python
# Write log body
with open(log_path, "w", encoding="utf-8") as log_file:
    log_file.write(f"=== Job #{job_id} started at {job.started_at} ===\n")
    # ... execute and stream output ...

# Mark job as completed (OUTSIDE file context)
old_state = job.state
job.complete(exit_code)  # Sets job.ended_at

# Write log footer (separate append operation)
with open(log_path, "a", encoding="utf-8") as log_file:
    log_file.write(f"=== Job #{job_id} ended at {job.ended_at} (exit code: {exit_code}) ===\n")
```

---

## Architectural Patterns

### Context-Aware Validation

**Pattern**: Validation rules change based on queue state and job positions.

**Example**: When queue is `started`, can only edit jobs AFTER the running job.

**Why**:
- **Safety**: Can't modify job that's currently executing or queued for immediate execution
- **User experience**: Allow editing upcoming jobs without stopping queue
- **Implementation**: `_is_job_editable()` checks both queue state and job position

**Code**:
```python
def _is_job_editable(self, job: Job) -> bool:
    if self.state == QUEUE_STATE_STOPPED:
        return True  # All jobs editable when stopped

    if job.is_running():
        return False  # Can never edit running job

    running_job = self._get_running_job_unlocked()
    if running_job is None:
        return True

    # Only jobs AFTER running job are editable
    return self.jobs.index(job) > self.jobs.index(running_job)
```

**Location**: `jqm/engine/queue.py:337-366`

### Internal Unlocked Helpers

**Pattern**: Public methods acquire lock, internal `_unlocked` helpers assume lock already held.

**Why**:
- **Avoid deadlock**: Can't call `get_job()` from within `delete_job()` - would try to acquire same lock twice
- **Composability**: Complex operations can call multiple helpers without lock overhead
- **Clear contract**: `_unlocked` suffix signals "caller must hold lock"

**Example**:
```python
def delete_job(self, job_id: int) -> None:
    with self._lock:  # Acquire lock
        job = self._get_job_unlocked(job_id)  # Use unlocked helper
        running_job = self._get_running_job_unlocked()  # Another helper
        # ... validation and deletion ...

def _get_job_unlocked(self, job_id: int) -> Job:
    # Assumes caller holds self._lock
    for job in self.jobs:
        if job.id == job_id:
            return job
    raise JobNotFoundError(f"Job {job_id} not found")
```

**Location**: `jqm/engine/queue.py:386-416`

### Error Messages with Context

**Pattern**: Include job ID, queue state, and running job ID in error messages.

**Why**:
- **Debugging**: User can see exactly why operation failed
- **Example bad message**: "Cannot delete job"
- **Example good message**: "Cannot delete job 5: job 3 is currently running and queue is started"
- **Implementation cost**: Minimal - just string formatting
- **User benefit**: Huge - immediately understand what's wrong

**Example**:
```python
raise InvalidOperationError(
    f"Cannot delete job {job_id}: job {running_id} is currently running "
    f"and queue is {self.state}"
)
```

**Location**: Throughout `jqm/engine/queue.py`

---

## Testing Strategies

### Unit vs Integration Tests

**Strategy**: Unit test components in isolation, integration tests verify end-to-end.

**Unit tests**:
- Mock dependencies (e.g., mock socket for protocol tests)
- Test single class in isolation
- Fast, focused, easy to debug

**Integration tests**:
- Real TCP connections
- Multiple components working together
- Slower but verify actual behavior

**Example**:
- Unit test: `test_protocol.py` mocks socket to test message framing
- Integration test: `test_engine_server.py` creates real server, connects real client

### Testing Concurrency

**Challenge**: Hard to reliably test thread safety without flaky tests.

**Approach**:
- Don't test threads directly (too flaky)
- Test the *effects* of proper locking (data consistency)
- Integration tests naturally exercise concurrent access
- Lock protects invariants - verify invariants hold

**Example**: `test_executor.py:test_sequential_execution()` verifies jobs complete in order, implicitly testing that executor and queue coordinate correctly.

### Test Isolation Techniques

**Problem**: Tests sharing state cause intermittent failures.

**Solutions applied**:
1. **Class-level server**: `setUpClass()` creates server once, `tearDownClass()` stops it
2. **Method-level cleanup**: `setUp()` cleans queue before each test
3. **Why not tearDown**: setUp guarantees clean state even if previous test crashed
4. **Independent clients**: Each test creates its own TCP connection

**Location**: `tests/test_engine_server.py:15-54`

---

## Key Takeaways for Future Development

1. **Thread safety first**: Always consider concurrent access when designing shared state
2. **Defensive copying**: Return copies of mutable data, never internal references
3. **Context in errors**: Help users understand *why* something failed, not just *that* it failed
4. **Test isolation**: Each test must work regardless of other tests' state
5. **Resource cleanup**: Use try/finally for resource management, especially with subprocesses
6. **Document the why**: Code shows what and how, comments/docs should explain why
7. **UTC for all timestamps**: Avoid timezone ambiguity from day one
8. **Protocol design matters**: Length-prefixed messages are cleaner than delimiter-based
9. **Separation of concerns**: Events from executor (knows execution), not dispatcher (knows commands)
10. **Lock granularity**: One lock is simpler and safer than complex fine-grained locking
