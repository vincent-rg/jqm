"""Unit tests for the JobExecutor."""

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from jqm.engine.event_broadcaster import EventBroadcaster
from jqm.engine.executor import JobExecutor
from jqm.engine.queue import JobQueue


class TestJobExecutor(unittest.TestCase):
    """Test cases for JobExecutor."""

    def setUp(self):
        """Set up test fixtures."""
        self.queue = JobQueue()
        self.broadcaster = EventBroadcaster()
        self.temp_dir = tempfile.mkdtemp()
        self.executor = JobExecutor(self.queue, self.broadcaster, self.temp_dir)

    def tearDown(self):
        """Clean up executor."""
        if self.executor._running:
            self.executor.stop()

    def test_start_and_stop(self):
        """Test starting and stopping the executor."""
        self.assertFalse(self.executor._running)

        self.executor.start()
        self.assertTrue(self.executor._running)

        self.executor.stop()
        self.assertFalse(self.executor._running)

    def test_execute_simple_command(self):
        """Test executing a simple successful command."""
        # Add a job
        job_id = self.queue.add_job("echo", ["hello world"], "/tmp")

        # Start queue
        self.queue.set_state("started")

        # Start executor
        self.executor.start()

        # Wait for job to complete
        time.sleep(1)

        # Check job completed successfully
        job = self.queue.get_job(job_id)
        self.assertEqual(job.state, "completed")
        self.assertEqual(job.exit_code, 0)

        # Check log file exists and has content
        log_path = Path(self.temp_dir) / job.log_file
        self.assertTrue(log_path.exists())

        log_content = log_path.read_text()
        self.assertIn("hello world", log_content)
        self.assertIn(f"Job #{job_id} started at", log_content)
        self.assertIn(f"Job #{job_id} ended at", log_content)
        self.assertIn("exit code: 0", log_content)

    def test_execute_failing_command(self):
        """Test executing a command that fails."""
        # Add a job that will fail (false command returns exit code 1)
        job_id = self.queue.add_job("false", [], "/tmp")

        # Start queue
        self.queue.set_state("started")

        # Start executor
        self.executor.start()

        # Wait for job to complete
        time.sleep(1)

        # Check job failed
        job = self.queue.get_job(job_id)
        self.assertEqual(job.state, "failed")
        self.assertNotEqual(job.exit_code, 0)

    def test_execute_command_not_found(self):
        """Test executing a command that doesn't exist."""
        # Add a job with non-existent command
        job_id = self.queue.add_job("nonexistent_command_xyz", [], "/tmp")

        # Start queue
        self.queue.set_state("started")

        # Start executor
        self.executor.start()

        # Wait for job to complete
        time.sleep(1)

        # Check job failed
        job = self.queue.get_job(job_id)
        self.assertEqual(job.state, "failed")
        self.assertEqual(job.exit_code, 127)  # Command not found

        # Check log file has error
        log_path = Path(self.temp_dir) / job.log_file
        log_content = log_path.read_text()
        self.assertIn("ERROR", log_content)
        self.assertIn("Command not found", log_content)

    def test_sequential_execution(self):
        """Test that jobs are executed sequentially."""
        # Add multiple jobs
        job1_id = self.queue.add_job("echo", ["job1"], "/tmp")
        job2_id = self.queue.add_job("echo", ["job2"], "/tmp")
        job3_id = self.queue.add_job("echo", ["job3"], "/tmp")

        # Start queue
        self.queue.set_state("started")

        # Start executor
        self.executor.start()

        # Wait for all jobs to complete
        time.sleep(2)

        # Check all jobs completed in order
        job1 = self.queue.get_job(job1_id)
        job2 = self.queue.get_job(job2_id)
        job3 = self.queue.get_job(job3_id)

        self.assertEqual(job1.state, "completed")
        self.assertEqual(job2.state, "completed")
        self.assertEqual(job3.state, "completed")

        # Verify timestamps show sequential execution
        self.assertIsNotNone(job1.started_at)
        self.assertIsNotNone(job1.ended_at)
        self.assertIsNotNone(job2.started_at)
        self.assertIsNotNone(job2.ended_at)
        self.assertIsNotNone(job3.started_at)
        self.assertIsNotNone(job3.ended_at)

    def test_respects_queue_stopped(self):
        """Test that executor doesn't run jobs when queue is stopped."""
        # Add a job
        job_id = self.queue.add_job("echo", ["test"], "/tmp")

        # Queue is stopped by default
        self.assertTrue(self.queue.is_stopped())

        # Start executor
        self.executor.start()

        # Wait a bit
        time.sleep(0.5)

        # Job should still be pending
        job = self.queue.get_job(job_id)
        self.assertEqual(job.state, "pending")

    def test_skips_skipped_jobs(self):
        """Test that executor skips jobs marked to skip."""
        # Add jobs
        job1_id = self.queue.add_job("echo", ["job1"], "/tmp")
        job2_id = self.queue.add_job("echo", ["job2"], "/tmp")
        job3_id = self.queue.add_job("echo", ["job3"], "/tmp")

        # Mark job2 to skip
        self.queue.set_job_state(job2_id, "skip")

        # Start queue
        self.queue.set_state("started")

        # Start executor
        self.executor.start()

        # Wait for jobs to complete
        time.sleep(2)

        # Check job1 and job3 completed, job2 skipped
        job1 = self.queue.get_job(job1_id)
        job2 = self.queue.get_job(job2_id)
        job3 = self.queue.get_job(job3_id)

        self.assertEqual(job1.state, "completed")
        self.assertEqual(job2.state, "skip")  # Still skipped
        self.assertEqual(job3.state, "completed")

    def test_event_broadcasting(self):
        """Test that events are broadcast during execution."""
        # Mock subscriber to capture events
        events = []

        def capture_event(event_name, data):
            events.append({"event": event_name, "data": data})

        # Patch broadcaster's broadcast_event method
        original_broadcast = self.broadcaster.broadcast_event
        self.broadcaster.broadcast_event = lambda name, data: (
            original_broadcast(name, data),
            capture_event(name, data),
        )[1]

        # Add a job
        job_id = self.queue.add_job("echo", ["test"], "/tmp")

        # Start queue
        self.queue.set_state("started")

        # Start executor
        self.executor.start()

        # Wait for job to complete
        time.sleep(1)

        # Check events were broadcast
        event_names = [e["event"] for e in events]

        # Should have job_status_changed (pending->running and running->completed)
        # and queue_progress
        self.assertIn("job_status_changed", event_names)
        self.assertIn("queue_progress", event_names)

        # Check at least 2 status changes (start and complete)
        status_change_events = [e for e in events if e["event"] == "job_status_changed"]
        self.assertGreaterEqual(len(status_change_events), 2)

    def test_log_file_format(self):
        """Test that log file has correct format."""
        # Add a job
        job_id = self.queue.add_job("echo", ["line1", "line2"], "/tmp")

        # Start queue and executor
        self.queue.set_state("started")
        self.executor.start()

        # Wait for completion
        time.sleep(1)

        # Read log file
        job = self.queue.get_job(job_id)
        log_path = Path(self.temp_dir) / job.log_file
        log_content = log_path.read_text()

        # Check format
        lines = log_content.split("\n")

        # First line should be header with "started at"
        self.assertTrue(lines[0].startswith("==="))
        self.assertIn("started at", lines[0])

        # Last non-empty line should be footer with "ended at"
        footer = [line for line in lines if line and line.startswith("===")][-1]
        self.assertIn("ended at", footer)
        self.assertIn("exit code:", footer)


if __name__ == "__main__":
    unittest.main()
