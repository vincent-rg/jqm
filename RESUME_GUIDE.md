# Resume Development Guide

Quick reference for resuming JQM development after a break.

## Current State

- **Branch**: `claude/job-queue-manager-Ukru1`
- **Last commit**: `7a3da8c` - Implement job execution with subprocess management
- **Tests passing**: 143/143 ✅
- **Engine status**: Fully functional and tested

## Quick Start Commands

```bash
# Verify you're on the right branch
git status
git log -1 --oneline

# Run all tests to verify everything works
python -m unittest discover tests -v

# See what's been implemented
cat IMPLEMENTATION_STATUS.md

# Understand design decisions
cat IMPLEMENTATION_NOTES.md
```

## Next Step: CLI Server (Step 5)

The CLI Server is a simple TCP relay:
1. Listens on port 9201 for CLI client connections
2. Forwards commands to Engine on port 5051
3. Returns responses to clients
4. Handles `subscribe` command for watch mode

**Estimated complexity**: Simple - much easier than previous steps.

**Why it's simple**:
- No business logic (just relay messages)
- Reuse existing protocol (`send_message`, `receive_message`)
- Pattern: Accept connection → forward to engine → relay response

**Files to create**:
- `jqm/cli_server/server.py` - CLIServer class
- `tests/test_cli_server.py` - Unit and integration tests

**Reference implementation**: Look at `jqm/engine/server.py` for TCP server pattern.

## Key Files Reference

### If you need to understand the protocol:
- `jqm/common/protocol.py` - How messages are sent/received

### If you need to understand the Engine:
- `jqm/engine/queue.py` - JobQueue class (state machine, thread safety)
- `jqm/engine/executor.py` - JobExecutor class (subprocess execution)
- `jqm/engine/server.py` - EngineServer class (TCP server pattern)

### If you need to understand why something was done a certain way:
- `IMPLEMENTATION_NOTES.md` - All design decisions with explanations

### If you need to see what's been tested:
- `tests/test_engine_server.py` - Integration test examples
- `tests/test_executor.py` - Execution test examples

## Common Patterns Used

### 1. TCP Server Pattern

```python
class MyServer:
    def __init__(self, host, port):
        self._server_socket = None
        self._running = False
        self._server_thread = None

    def start(self):
        self._running = True
        self._server_thread = threading.Thread(target=self._run_server, daemon=True)
        self._server_thread.start()

    def _run_server(self):
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)

        while self._running:
            client_socket, _ = self._server_socket.accept()
            # Handle client in separate thread
            threading.Thread(target=self._handle_client, args=(client_socket,), daemon=True).start()
```

### 2. Protocol Usage

```python
from jqm.common.protocol import send_message, receive_message, create_response

# Receiving
message = receive_message(client_socket)
cmd = message.get("cmd")

# Sending
response = create_response(success=True, data={"result": 42})
send_message(client_socket, response)
```

### 3. Thread-Safe State

```python
class MyClass:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = {}

    def public_method(self):
        with self._lock:
            # Safe to access shared state
            pass
```

### 4. Integration Test Setup

```python
class TestMyServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create server once for all tests
        cls.server = MyServer(host="127.0.0.1", port=0)
        cls.server.start()
        time.sleep(0.1)  # Let server start
        cls.port = cls.server._server_socket.getsockname()[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        # Create fresh client for each test
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.connect(("127.0.0.1", self.port))

    def tearDown(self):
        self.client.close()
```

## Ground Rules (Reminder)

From the original conversation:

1. **Commit frequently** - After each working feature
2. **Don't assume bugs** - Test assumptions before fixing
3. **Write small functions** - Single responsibility
4. **Write unit tests** - Cover edge cases
5. **Use Python logging** - Not print statements
6. **No "co-authored" footers** - Keep commit messages clean
7. **Thread safety** - Consider concurrent access
8. **Defensive copying** - Return copies of mutable data
9. **UTC timestamps** - Always use timezone-aware datetimes
10. **Contextual errors** - Include relevant IDs and state in error messages

## Environment

- **Python version**: 3.9.13
- **No third-party packages**: Use only standard library
- **Platform**: Linux (but should work on Windows too)
- **Git branch**: `claude/job-queue-manager-Ukru1`

## Testing Checklist

Before committing:

```bash
# Run all tests
python -m unittest discover tests -v

# Verify test count
# Should see "Ran XXX tests in X.XXXs" and "OK"

# Check for warnings
# Address any ResourceWarning or DeprecationWarning
```

## Commit Message Format

```
Short description (50 chars or less)

Longer explanation if needed (wrap at 72 chars):
- What was implemented
- Why it was done this way
- What tests were added

No "Co-authored-by" footer
```

## If Tests Fail

1. **Don't panic** - Read the error message carefully
2. **Isolate the problem** - Run single test: `python -m unittest tests.test_module.TestClass.test_method`
3. **Check assumptions** - Use print() or debugger to verify state
4. **Review similar code** - Look at working tests for patterns
5. **Check IMPLEMENTATION_NOTES.md** - See if similar problem was solved before

## Useful Git Commands

```bash
# See what's changed since last commit
git status
git diff

# Commit with message
git commit -m "Short description"

# Push to remote
git push -u origin claude/job-queue-manager-Ukru1

# View commit history
git log --oneline -10

# See details of specific commit
git show 7a3da8c
```

## Documentation Files

- **SPECIFICATIONS.md** - Complete project spec (translated from French)
- **DEVELOPMENT_GUIDELINES.md** - Coding standards and best practices
- **IMPLEMENTATION_STATUS.md** - What's done, what's pending
- **IMPLEMENTATION_NOTES.md** - Design decisions and lessons learned (THE MOST IMPORTANT)
- **README.md** - Project overview and usage
- **RESUME_GUIDE.md** - This file - quick reference for resuming

## Questions to Ask When Implementing

1. **Thread safety**: Will this be accessed from multiple threads?
2. **Resource cleanup**: Do I need finally blocks to clean up resources?
3. **Error messages**: Will the user understand what went wrong and why?
4. **Test isolation**: Can this test run independently and in any order?
5. **Edge cases**: What if the input is empty, None, or unexpected?
6. **Why this way**: Can I explain in IMPLEMENTATION_NOTES.md why I chose this approach?

## Ready to Continue?

Read the next step details in IMPLEMENTATION_STATUS.md, then:

1. Create the implementation files
2. Write tests as you go
3. Run tests frequently
4. Commit when tests pass
5. Update IMPLEMENTATION_STATUS.md
6. Update IMPLEMENTATION_NOTES.md with any new design decisions

Good luck! 🚀
