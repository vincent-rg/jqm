"""Job queue management with state machine."""

import logging
from typing import Optional

from jqm.common.constants import (
    QUEUE_STATE_PAUSED,
    QUEUE_STATE_STARTED,
    QUEUE_STATE_STOPPED,
    REORDER_BOTTOM,
    REORDER_DOWN,
    REORDER_TOP,
    REORDER_UP,
    STATE_PENDING,
    STATE_SKIP,
)
from jqm.engine.job import Job

logger = logging.getLogger(__name__)


class QueueError(Exception):
    """Base exception for queue operations."""
    pass


class JobNotFoundError(QueueError):
    """Raised when a job ID is not found."""
    pass


class InvalidOperationError(QueueError):
    """Raised when an operation is not allowed in current state."""
    pass


class JobQueue:
    """Manages the job queue and queue state.

    Handles job operations (add, delete, update, reorder) with validation
    based on queue state and job state.

    Attributes:
        state: Current queue state (stopped/started/paused)
        jobs: List of jobs in execution order
    """

    def __init__(self):
        """Initialize an empty job queue."""
        self.state = QUEUE_STATE_STOPPED
        self.jobs: list[Job] = []
        self._next_job_id = 1

    def get_state(self) -> str:
        """Get current queue state.

        Returns:
            Queue state string (stopped/started/paused)
        """
        return self.state

    def set_state(self, new_state: str) -> None:
        """Set queue state.

        Args:
            new_state: New queue state (stopped/started/paused)

        Raises:
            ValueError: If new_state is invalid
        """
        valid_states = (QUEUE_STATE_STOPPED, QUEUE_STATE_STARTED, QUEUE_STATE_PAUSED)
        if new_state not in valid_states:
            raise ValueError(f"Invalid queue state: {new_state}")

        old_state = self.state
        self.state = new_state
        logger.info(f"Queue state changed: {old_state} -> {new_state}")

    def is_stopped(self) -> bool:
        """Check if queue is stopped."""
        return self.state == QUEUE_STATE_STOPPED

    def is_started(self) -> bool:
        """Check if queue is started."""
        return self.state == QUEUE_STATE_STARTED

    def is_paused(self) -> bool:
        """Check if queue is paused."""
        return self.state == QUEUE_STATE_PAUSED

    def add_job(self, command: str, args: list[str], cwd: str) -> int:
        """Add a new job to the queue.

        Args:
            command: Command to execute
            args: Command arguments
            cwd: Working directory

        Returns:
            ID of the created job
        """
        job_id = self._next_job_id
        self._next_job_id += 1

        job = Job(job_id, command, args, cwd)
        self.jobs.append(job)

        logger.info(f"Added job {job_id}: {command}")
        return job_id

    def get_job(self, job_id: int) -> Job:
        """Get a job by ID.

        Args:
            job_id: Job ID to find

        Returns:
            Job object

        Raises:
            JobNotFoundError: If job ID not found
        """
        for job in self.jobs:
            if job.id == job_id:
                return job
        raise JobNotFoundError(f"Job {job_id} not found")

    def get_all_jobs(self) -> list[Job]:
        """Get all jobs in the queue.

        Returns:
            List of all jobs
        """
        return self.jobs.copy()

    def delete_job(self, job_id: int) -> None:
        """Delete a job from the queue.

        Args:
            job_id: Job ID to delete

        Raises:
            JobNotFoundError: If job not found
            InvalidOperationError: If job cannot be deleted in current state
        """
        job = self.get_job(job_id)

        # Cannot delete running job
        if job.is_running():
            raise InvalidOperationError("Cannot delete running job")

        # If queue is started/paused, can only delete jobs after running job
        if self.state in (QUEUE_STATE_STARTED, QUEUE_STATE_PAUSED):
            if not self._is_job_editable(job):
                raise InvalidOperationError(
                    "Cannot delete job before running job when queue is started"
                )

        self.jobs.remove(job)
        logger.info(f"Deleted job {job_id}")

    def update_job(self, job_id: int, command: str, args: list[str], cwd: str) -> None:
        """Update a job's command and arguments.

        Args:
            job_id: Job ID to update
            command: New command
            args: New arguments
            cwd: New working directory

        Raises:
            JobNotFoundError: If job not found
            InvalidOperationError: If job cannot be updated in current state
        """
        job = self.get_job(job_id)

        # Cannot update running job
        if job.is_running():
            raise InvalidOperationError("Cannot update running job")

        # If queue is started/paused, can only update jobs after running job
        if self.state in (QUEUE_STATE_STARTED, QUEUE_STATE_PAUSED):
            if not self._is_job_editable(job):
                raise InvalidOperationError(
                    "Cannot update job before running job when queue is started"
                )

        job.update(command, args, cwd)
        logger.info(f"Updated job {job_id}")

    def set_job_state(self, job_id: int, new_state: str) -> None:
        """Set a job's state (pending or skip).

        Args:
            job_id: Job ID to modify
            new_state: New state (pending or skip)

        Raises:
            JobNotFoundError: If job not found
            InvalidOperationError: If state change not allowed
            ValueError: If new_state is invalid
        """
        job = self.get_job(job_id)

        # Can only toggle between pending and skip
        if new_state not in (STATE_PENDING, STATE_SKIP):
            raise ValueError(f"Can only set state to 'pending' or 'skip', got: {new_state}")

        # Cannot change state of running job
        if job.is_running():
            raise InvalidOperationError("Cannot change state of running job")

        if new_state == STATE_PENDING:
            job.set_pending()
        else:
            job.set_skip()

        logger.info(f"Set job {job_id} state to {new_state}")

    def reorder_job(self, job_id: int, action: str) -> None:
        """Reorder a job in the queue.

        Args:
            job_id: Job ID to reorder
            action: Reorder action (top/bottom/up/down)

        Raises:
            JobNotFoundError: If job not found
            InvalidOperationError: If job cannot be reordered
            ValueError: If action is invalid
        """
        valid_actions = (REORDER_TOP, REORDER_BOTTOM, REORDER_UP, REORDER_DOWN)
        if action not in valid_actions:
            raise ValueError(f"Invalid reorder action: {action}")

        job = self.get_job(job_id)

        # Cannot reorder running job
        if job.is_running():
            raise InvalidOperationError("Cannot reorder running job")

        # If queue is started/paused, can only reorder jobs after running job
        if self.state in (QUEUE_STATE_STARTED, QUEUE_STATE_PAUSED):
            if not self._is_job_editable(job):
                raise InvalidOperationError(
                    "Cannot reorder job before running job when queue is started"
                )

        # Get current position
        current_index = self.jobs.index(job)

        # Calculate new position based on action
        if action == REORDER_TOP:
            new_index = self._get_first_editable_index()
        elif action == REORDER_BOTTOM:
            new_index = len(self.jobs) - 1
        elif action == REORDER_UP:
            new_index = max(self._get_first_editable_index(), current_index - 1)
        else:  # REORDER_DOWN
            new_index = min(len(self.jobs) - 1, current_index + 1)

        # Move job to new position
        if new_index != current_index:
            self.jobs.pop(current_index)
            self.jobs.insert(new_index, job)
            logger.info(f"Reordered job {job_id}: {action}")

    def get_running_job(self) -> Optional[Job]:
        """Get the currently running job, if any.

        Returns:
            Running job or None if no job is running
        """
        for job in self.jobs:
            if job.is_running():
                return job
        return None

    def get_next_executable_job(self) -> Optional[Job]:
        """Get the next job that should be executed.

        Returns the first pending (non-skipped) job that comes after the
        running job, or the first pending job if no job is running.

        Returns:
            Next job to execute, or None if queue is empty/all done
        """
        running_job = self.get_running_job()

        # Find starting point for search
        start_index = 0
        if running_job is not None:
            start_index = self.jobs.index(running_job) + 1

        # Find first pending job after start_index
        for i in range(start_index, len(self.jobs)):
            job = self.jobs[i]
            if job.is_pending():
                return job

        return None

    def _is_job_editable(self, job: Job) -> bool:
        """Check if a job can be edited in current queue state.

        Args:
            job: Job to check

        Returns:
            True if job can be edited, False otherwise
        """
        # If queue is stopped, all jobs are editable
        if self.is_stopped():
            return True

        # Cannot edit running job
        if job.is_running():
            return False

        # If queue is started/paused, only jobs after running job are editable
        running_job = self.get_running_job()
        if running_job is None:
            # No running job, all are editable
            return True

        # Check if job comes after running job
        running_index = self.jobs.index(running_job)
        job_index = self.jobs.index(job)

        return job_index > running_index

    def _get_first_editable_index(self) -> int:
        """Get the index of the first editable job position.

        Returns:
            Index where editable jobs start
        """
        if self.is_stopped():
            return 0

        running_job = self.get_running_job()
        if running_job is None:
            return 0

        # First editable position is after running job
        return self.jobs.index(running_job) + 1

    def get_queue_info(self) -> dict:
        """Get queue state information.

        Returns:
            Dictionary with queue state, current job, and totals
        """
        running_job = self.get_running_job()

        info = {
            "state": self.state,
            "total_jobs": len(self.jobs),
            "current_job": None,
            "current_job_started_at": None,
        }

        if running_job is not None:
            # Find position of running job (1-indexed for display)
            position = self.jobs.index(running_job) + 1
            info["current_job"] = position
            info["current_job_started_at"] = running_job.started_at

        return info
