"""Job class representing a single job in the queue."""

from datetime import datetime
from typing import Optional

from jqm.common.constants import (
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_PENDING,
    STATE_RUNNING,
    STATE_SKIP,
)


class Job:
    """Represents a single job with command, arguments, and state.

    Attributes:
        id: Unique job identifier (auto-assigned)
        command: Command to execute
        args: List of command arguments
        cwd: Working directory for execution
        state: Current job state (pending/running/completed/failed/skip)
        to_skip: Persistent flag indicating if job should be skipped
        exit_code: Process exit code (None until completed)
        log_file: Path to log file for this job
        started_at: ISO datetime when job started
        ended_at: ISO datetime when job ended
    """

    def __init__(
        self,
        job_id: int,
        command: str,
        args: list[str],
        cwd: str,
        to_skip: bool = False,
    ):
        """Initialize a new job.

        Args:
            job_id: Unique identifier for this job
            command: Command to execute
            args: List of command arguments
            cwd: Working directory
            to_skip: Whether to skip this job during execution
        """
        self.id = job_id
        self.command = command
        self.args = args
        self.cwd = cwd
        self.to_skip = to_skip

        # Volatile state (not persisted in export)
        self.state = STATE_SKIP if to_skip else STATE_PENDING
        self.exit_code: Optional[int] = None
        self.log_file = f"job_{job_id:03d}.log"
        self.started_at: Optional[str] = None
        self.ended_at: Optional[str] = None

    def is_running(self) -> bool:
        """Check if job is currently running."""
        return self.state == STATE_RUNNING

    def is_completed(self) -> bool:
        """Check if job has completed (success or failure)."""
        return self.state in (STATE_COMPLETED, STATE_FAILED)

    def is_pending(self) -> bool:
        """Check if job is pending execution."""
        return self.state == STATE_PENDING

    def is_skipped(self) -> bool:
        """Check if job is marked to skip."""
        return self.state == STATE_SKIP

    def can_edit(self) -> bool:
        """Check if job can be edited/deleted/reordered.

        Returns:
            True if job is not running, False otherwise
        """
        return self.state != STATE_RUNNING

    def set_pending(self) -> None:
        """Mark job as pending (ready to run)."""
        if self.state == STATE_RUNNING:
            raise ValueError("Cannot change state of running job")
        self.state = STATE_PENDING
        self.to_skip = False

    def set_skip(self) -> None:
        """Mark job to be skipped."""
        if self.state == STATE_RUNNING:
            raise ValueError("Cannot change state of running job")
        self.state = STATE_SKIP
        self.to_skip = True

    def start(self) -> None:
        """Mark job as running and record start time."""
        if self.state == STATE_RUNNING:
            raise ValueError("Job is already running")
        self.state = STATE_RUNNING
        self.started_at = datetime.now().isoformat()
        self.exit_code = None
        self.ended_at = None

    def complete(self, exit_code: int) -> None:
        """Mark job as completed with exit code.

        Args:
            exit_code: Process exit code (0 = success, non-zero = failure)
        """
        if self.state != STATE_RUNNING:
            raise ValueError("Can only complete a running job")

        self.exit_code = exit_code
        self.ended_at = datetime.now().isoformat()

        if exit_code == 0:
            self.state = STATE_COMPLETED
        else:
            self.state = STATE_FAILED

    def update(self, command: str, args: list[str], cwd: str) -> None:
        """Update job command and arguments.

        Args:
            command: New command
            args: New arguments
            cwd: New working directory

        Raises:
            ValueError: If job is currently running
        """
        if self.state == STATE_RUNNING:
            raise ValueError("Cannot update running job")

        self.command = command
        self.args = args
        self.cwd = cwd

    def to_dict(self) -> dict:
        """Convert job to dictionary representation.

        Returns:
            Dictionary with all job fields
        """
        return {
            "id": self.id,
            "command": self.command,
            "args": self.args,
            "cwd": self.cwd,
            "state": self.state,
            "to_skip": self.to_skip,
            "exit_code": self.exit_code,
            "log_file": self.log_file,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"Job(id={self.id}, command={self.command}, state={self.state})"
