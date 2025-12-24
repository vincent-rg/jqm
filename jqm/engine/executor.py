"""Job execution engine.

Manages sequential job execution with subprocess management and event broadcasting.
"""

import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from jqm.common.constants import QUEUE_STATE_STARTED
from jqm.engine.event_broadcaster import EventBroadcaster
from jqm.engine.queue import JobQueue

logger = logging.getLogger(__name__)


class JobExecutor:
    """Executes jobs from the queue sequentially.

    Runs in a background thread and processes jobs one at a time.
    Captures stdout/stderr to log files and broadcasts events.
    """

    def __init__(
        self,
        queue: JobQueue,
        broadcaster: EventBroadcaster,
        log_dir: str,
    ):
        """Initialize the job executor.

        Args:
            queue: JobQueue to process
            broadcaster: EventBroadcaster for sending events
            log_dir: Directory where log files are written
        """
        self.queue = queue
        self.broadcaster = broadcaster
        self.log_dir = Path(log_dir)

        self._running = False
        self._executor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the executor thread."""
        if self._running:
            logger.warning("JobExecutor is already running")
            return

        self._running = True
        self._stop_event.clear()
        self._executor_thread = threading.Thread(target=self._run, daemon=True)
        self._executor_thread.start()

        logger.info("JobExecutor started")

    def stop(self) -> None:
        """Stop the executor thread."""
        if not self._running:
            return

        logger.info("Stopping JobExecutor...")
        self._running = False
        self._stop_event.set()

        if self._executor_thread and self._executor_thread.is_alive():
            self._executor_thread.join(timeout=5)

        logger.info("JobExecutor stopped")

    def _run(self) -> None:
        """Main executor loop (runs in background thread)."""
        logger.info("JobExecutor thread started")

        try:
            while self._running:
                # Check if queue is started
                if not self.queue.is_started():
                    # Queue is stopped or paused, wait a bit
                    self._stop_event.wait(timeout=0.5)
                    continue

                # Get next job to execute
                next_job = self.queue.get_next_executable_job()

                if next_job is None:
                    # No more jobs to execute
                    # Check if we should stop the queue (all done)
                    running_job = self.queue.get_running_job()
                    if running_job is None:
                        # All jobs done, queue stays in started state
                        # but there's nothing to do
                        logger.debug("No pending jobs, waiting...")
                        self._stop_event.wait(timeout=0.5)
                    else:
                        # There's a running job, wait for it to complete
                        # (This shouldn't happen since we execute synchronously)
                        logger.warning("Running job exists but no pending jobs")
                        self._stop_event.wait(timeout=0.5)
                    continue

                # Execute the job
                try:
                    self._execute_job(next_job.id)
                except Exception as e:
                    logger.error(f"Error executing job {next_job.id}: {e}", exc_info=True)
                    # Continue to next job

                # Small delay before checking for next job
                self._stop_event.wait(timeout=0.1)

        except Exception as e:
            logger.error(f"JobExecutor thread error: {e}", exc_info=True)
        finally:
            logger.info("JobExecutor thread stopped")

    def _execute_job(self, job_id: int) -> None:
        """Execute a single job.

        Args:
            job_id: ID of job to execute
        """
        # Get the job (with lock)
        job = self.queue.get_job(job_id)

        logger.info(f"Executing job {job_id}: {job.command} {' '.join(job.args)}")

        # Mark job as running
        old_state = job.state
        job.start()

        # Broadcast job status changed event
        self.broadcaster.broadcast_job_status_changed(
            job_id=job_id,
            old_state=old_state,
            new_state=job.state,
            started_at=job.started_at,
        )

        # Broadcast queue progress event
        queue_info = self.queue.get_queue_info()
        self.broadcaster.broadcast_queue_progress(
            current_job=queue_info["current_job"] or 0,
            total_jobs=queue_info["total_jobs"],
            job_id=job_id,
            command=job.command,
            started_at=job.started_at or "",
        )

        # Prepare log file
        log_path = self.log_dir / job.log_file

        # Write log header
        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"=== Job #{job_id} started at {job.started_at} ===\n")
            log_file.flush()

            # Execute subprocess
            try:
                process = subprocess.Popen(
                    [job.command] + job.args,
                    cwd=job.cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # Merge stderr into stdout
                    text=True,
                    bufsize=1,  # Line buffered
                )

                # Stream output to log file
                try:
                    if process.stdout:
                        for line in process.stdout:
                            log_file.write(line)
                            log_file.flush()

                    # Wait for process to complete
                    exit_code = process.wait()
                finally:
                    # Ensure stdout is closed
                    if process.stdout:
                        process.stdout.close()

            except FileNotFoundError as e:
                # Command not found
                log_file.write(f"\nERROR: Command not found: {job.command}\n")
                log_file.write(f"{e}\n")
                exit_code = 127  # Standard "command not found" exit code

            except Exception as e:
                # Other execution errors
                log_file.write(f"\nERROR: Failed to execute command: {e}\n")
                exit_code = 1

        # Mark job as completed (outside the file context to get ended_at)
        old_state = job.state
        job.complete(exit_code)

        # Write log footer
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"=== Job #{job_id} ended at {job.ended_at} (exit code: {exit_code}) ===\n")

        # Broadcast job status changed event
        self.broadcaster.broadcast_job_status_changed(
            job_id=job_id,
            old_state=old_state,
            new_state=job.state,
        )

        if exit_code == 0:
            logger.info(f"Job {job_id} completed successfully")
        else:
            logger.warning(f"Job {job_id} failed with exit code {exit_code}")
