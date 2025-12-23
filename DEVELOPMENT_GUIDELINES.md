# JQM Development Guidelines

## Ground Rules

### Version Control
- **Commit frequently** - Small, atomic commits
- **No "Co-authored-by" footers** in commit messages
- **Clear commit messages** - Describe what and why, not how

### Debugging
- **Never make assumptions** - Always test to verify bug causes
- **Add tests first** - Write unit tests to reproduce bugs
- **Add logs** - Use Python's logging module to trace execution
- **No blind fixes** - Understand the root cause before fixing

### Code Quality

#### Function Design
- **Single Responsibility** - Each function does one thing well
- **Small functions** - Keep them short and focused
- **Consistent style** - Follow the same patterns throughout

#### Type Safety
- **Type hints** - Use Python type hints for all function signatures
- **Example**: `def add_job(command: str, args: list[str], cwd: str) -> int:`

#### Documentation
- **Docstrings** - For all public functions and classes
- **Format**: Google or NumPy style
- **Comments** - Only for "why", not "what" (code should be self-explanatory)
- **No obvious comments** - Don't comment what's already clear from code

#### Constants and Configuration
- **No magic numbers** - Use named constants
- **No magic strings** - Define string literals as constants
- **Centralized config** - Keep defaults in one place (constants module)
- **Example**:
  ```python
  # Bad
  socket.bind(("localhost", 5051))

  # Good
  DEFAULT_ENGINE_PORT = 5051
  DEFAULT_ENGINE_HOST = "localhost"
  socket.bind((DEFAULT_ENGINE_HOST, DEFAULT_ENGINE_PORT))
  ```

#### Error Handling
- **Explicit exceptions** - Handle expected errors explicitly
- **Meaningful messages** - Include context in error messages
- **Don't swallow errors** - Log or re-raise, don't ignore
- **Fail fast** - Validate inputs early

#### DRY Principle
- **Don't Repeat Yourself** - Extract common code
- **Shared utilities** - Especially for TCP/JSON messaging
- **Reusable components** - Protocol encoding/decoding in one place

### Project Structure

#### Separation of Concerns
- **Protocol layer** - TCP/JSON message formatting
- **Business logic** - Job management, queue logic
- **I/O layer** - File operations, subprocess execution
- **Keep them separate** - Easy to test and maintain

#### Module Organization
```
jqm/
├── common/           # Shared code (protocol, constants)
├── engine/           # Engine implementation
├── http_server/      # HTTP server
├── cli_server/       # CLI server
├── cli_client/       # CLI client
└── tests/            # Unit tests
```

### Testing

#### Unit Tests
- **Test coverage** - Aim for high coverage of business logic
- **Test isolation** - Each test is independent
- **Shared fixtures** - Use pytest fixtures for common setup
- **Test naming** - `test_<what>_<condition>_<expected_result>`
- **Example**: `test_add_job_when_queue_running_raises_error`

#### Test Organization
- **Mirror source structure** - tests/ mirrors src/ structure
- **Test utilities** - Shared helpers in tests/conftest.py
- **Mock external dependencies** - TCP connections, subprocess, file I/O

#### What to Test
- **Business logic** - Core functionality (job management, queue states)
- **Edge cases** - Boundary conditions, error cases
- **State transitions** - Queue and job state changes
- **API contracts** - Request/response formats

#### What Not to Test
- **Third-party code** - Don't test Python standard library
- **Simple getters/setters** - Unless they have logic
- **Integration details** - Unit tests focus on units

### Logging

#### Log Levels
- **DEBUG** - Detailed diagnostic info (message contents, state changes)
- **INFO** - General informational messages (job started/completed)
- **WARNING** - Something unexpected but handled
- **ERROR** - Error condition that was handled
- **CRITICAL** - Serious error, application may crash

#### Log Format
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
```

#### What to Log
- **State changes** - Job/queue state transitions
- **External operations** - File I/O, subprocess execution, network
- **Error conditions** - With context and stack traces
- **Important events** - Job start/end, queue start/stop

#### What Not to Log
- **Sensitive data** - Passwords, tokens (not applicable here but good practice)
- **Too much detail at INFO** - Save verbose details for DEBUG
- **Inside tight loops** - Can impact performance

### Security Considerations

⚠️ **JQM has NO built-in security** - This is by design for v1

- **Localhost only** - Bind to 127.0.0.1, not 0.0.0.0
- **No authentication** - Documented limitation
- **Arbitrary command execution** - User is responsible for trust
- **Document clearly** - Security limitations in README

### Performance

#### Avoid Over-Engineering
- **YAGNI** - You Aren't Gonna Need It
- **Simple solutions first** - Optimize only when needed
- **No premature abstraction** - Three instances before extracting

#### Threading
- **Minimal threads** - Only where necessary (job execution, event broadcast)
- **Thread safety** - Use locks for shared state
- **Clean shutdown** - Join threads properly on exit

### Code Review Checklist

Before committing, check:
- [ ] Type hints on all functions
- [ ] Docstrings on public functions
- [ ] No magic numbers/strings
- [ ] Error handling in place
- [ ] Logging at appropriate levels
- [ ] Unit tests written and passing
- [ ] No code duplication
- [ ] Clear variable/function names
- [ ] Consistent formatting (use `black` formatter if available)

## Python-Specific Guidelines

### Style
- **PEP 8** - Follow Python style guide
- **Line length** - Max 100 characters (slightly relaxed from 79)
- **Naming conventions**:
  - `snake_case` for functions and variables
  - `PascalCase` for classes
  - `UPPER_SNAKE_CASE` for constants

### Modern Python Features (3.9.13)
- **f-strings** - For string formatting
- **Type hints** - Use `list[str]` not `List[str]` (3.9+ style)
- **Pathlib** - Use `Path` instead of `os.path` where appropriate
- **Context managers** - `with` statements for resources
- **Dictionary merge** - Use `|` operator (Python 3.9+)

### Avoid
- **Global variables** - Pass state explicitly
- **Circular imports** - Design module hierarchy carefully
- **Bare except** - Always specify exception types
- **Mutable default arguments** - Use `None` and initialize inside

## Example: Good vs Bad

### Bad
```python
def process(data):
    # Process the data
    result = []
    for item in data:
        if item > 10:
            result.append(item * 2)
    return result
```

### Good
```python
def filter_and_double(values: list[int], threshold: int = 10) -> list[int]:
    """Filter values above threshold and double them.

    Args:
        values: List of integers to process
        threshold: Minimum value to include (default: 10)

    Returns:
        List of doubled values that exceed threshold
    """
    return [value * 2 for value in values if value > threshold]
```

## Resources

- [PEP 8 - Style Guide for Python Code](https://peps.python.org/pep-0008/)
- [PEP 257 - Docstring Conventions](https://peps.python.org/pep-0257/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [Python Logging HOWTO](https://docs.python.org/3/howto/logging.html)

---

**Remember**: These are guidelines, not rigid rules. Use good judgment and prioritize readability and maintainability.
