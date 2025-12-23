"""Unit tests for the Job class."""

import unittest
from datetime import datetime

from jqm.common.constants import (
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_PENDING,
    STATE_RUNNING,
    STATE_SKIP,
)
from jqm.engine.job import Job


class TestJobInitialization(unittest.TestCase):
    """Test cases for Job initialization."""

    def test_create_job_defaults(self):
        """Test creating a job with default values."""
        job = Job(1, "python", ["script.py"], "/tmp")

        self.assertEqual(job.id, 1)
        self.assertEqual(job.command, "python")
        self.assertEqual(job.args, ["script.py"])
        self.assertEqual(job.cwd, "/tmp")
        self.assertEqual(job.state, STATE_PENDING)
        self.assertFalse(job.to_skip)
        self.assertIsNone(job.exit_code)
        self.assertEqual(job.log_file, "job_001.log")
        self.assertIsNone(job.started_at)
        self.assertIsNone(job.ended_at)

    def test_create_job_with_skip(self):
        """Test creating a job with to_skip=True."""
        job = Job(2, "echo", ["hello"], "/", to_skip=True)

        self.assertEqual(job.state, STATE_SKIP)
        self.assertTrue(job.to_skip)

    def test_log_file_formatting(self):
        """Test log file name formatting with zero padding."""
        job1 = Job(1, "cmd", [], "/")
        job2 = Job(42, "cmd", [], "/")
        job3 = Job(999, "cmd", [], "/")

        self.assertEqual(job1.log_file, "job_001.log")
        self.assertEqual(job2.log_file, "job_042.log")
        self.assertEqual(job3.log_file, "job_999.log")


class TestJobStateChecks(unittest.TestCase):
    """Test cases for job state checking methods."""

    def test_is_running(self):
        """Test is_running method."""
        job = Job(1, "cmd", [], "/")
        self.assertFalse(job.is_running())

        job.start()
        self.assertTrue(job.is_running())

        job.complete(0)
        self.assertFalse(job.is_running())

    def test_is_completed(self):
        """Test is_completed method."""
        job = Job(1, "cmd", [], "/")
        self.assertFalse(job.is_completed())

        job.start()
        self.assertFalse(job.is_completed())

        job.complete(0)
        self.assertTrue(job.is_completed())

    def test_is_completed_on_failure(self):
        """Test is_completed returns True for failed jobs."""
        job = Job(1, "cmd", [], "/")
        job.start()
        job.complete(1)

        self.assertTrue(job.is_completed())
        self.assertEqual(job.state, STATE_FAILED)

    def test_is_pending(self):
        """Test is_pending method."""
        job = Job(1, "cmd", [], "/")
        self.assertTrue(job.is_pending())

        job.set_skip()
        self.assertFalse(job.is_pending())

        job.set_pending()
        self.assertTrue(job.is_pending())

    def test_is_skipped(self):
        """Test is_skipped method."""
        job = Job(1, "cmd", [], "/")
        self.assertFalse(job.is_skipped())

        job.set_skip()
        self.assertTrue(job.is_skipped())

    def test_can_edit(self):
        """Test can_edit method."""
        job = Job(1, "cmd", [], "/")
        self.assertTrue(job.can_edit())

        job.start()
        self.assertFalse(job.can_edit())

        job.complete(0)
        self.assertTrue(job.can_edit())


class TestJobStateTransitions(unittest.TestCase):
    """Test cases for job state transitions."""

    def test_set_pending(self):
        """Test setting job to pending state."""
        job = Job(1, "cmd", [], "/", to_skip=True)
        self.assertEqual(job.state, STATE_SKIP)
        self.assertTrue(job.to_skip)

        job.set_pending()
        self.assertEqual(job.state, STATE_PENDING)
        self.assertFalse(job.to_skip)

    def test_set_skip(self):
        """Test setting job to skip state."""
        job = Job(1, "cmd", [], "/")
        self.assertEqual(job.state, STATE_PENDING)
        self.assertFalse(job.to_skip)

        job.set_skip()
        self.assertEqual(job.state, STATE_SKIP)
        self.assertTrue(job.to_skip)

    def test_cannot_set_pending_when_running(self):
        """Test that running job cannot be set to pending."""
        job = Job(1, "cmd", [], "/")
        job.start()

        with self.assertRaises(ValueError) as ctx:
            job.set_pending()
        self.assertIn("running", str(ctx.exception).lower())

    def test_cannot_set_skip_when_running(self):
        """Test that running job cannot be set to skip."""
        job = Job(1, "cmd", [], "/")
        job.start()

        with self.assertRaises(ValueError) as ctx:
            job.set_skip()
        self.assertIn("running", str(ctx.exception).lower())

    def test_start_job(self):
        """Test starting a job."""
        job = Job(1, "cmd", [], "/")

        job.start()

        self.assertEqual(job.state, STATE_RUNNING)
        self.assertIsNotNone(job.started_at)
        self.assertIsNone(job.exit_code)
        self.assertIsNone(job.ended_at)

        # Verify started_at is valid ISO datetime
        datetime.fromisoformat(job.started_at)

    def test_cannot_start_running_job(self):
        """Test that already running job cannot be started again."""
        job = Job(1, "cmd", [], "/")
        job.start()

        with self.assertRaises(ValueError) as ctx:
            job.start()
        self.assertIn("already running", str(ctx.exception).lower())

    def test_complete_job_success(self):
        """Test completing a job successfully."""
        job = Job(1, "cmd", [], "/")
        job.start()

        job.complete(0)

        self.assertEqual(job.state, STATE_COMPLETED)
        self.assertEqual(job.exit_code, 0)
        self.assertIsNotNone(job.ended_at)

        # Verify ended_at is valid ISO datetime
        datetime.fromisoformat(job.ended_at)

    def test_complete_job_failure(self):
        """Test completing a job with failure."""
        job = Job(1, "cmd", [], "/")
        job.start()

        job.complete(1)

        self.assertEqual(job.state, STATE_FAILED)
        self.assertEqual(job.exit_code, 1)
        self.assertIsNotNone(job.ended_at)

    def test_cannot_complete_non_running_job(self):
        """Test that only running jobs can be completed."""
        job = Job(1, "cmd", [], "/")

        with self.assertRaises(ValueError) as ctx:
            job.complete(0)
        self.assertIn("running", str(ctx.exception).lower())


class TestJobUpdate(unittest.TestCase):
    """Test cases for job update operations."""

    def test_update_job(self):
        """Test updating job command and arguments."""
        job = Job(1, "python", ["old.py"], "/tmp")

        job.update("bash", ["new.sh", "--flag"], "/home")

        self.assertEqual(job.command, "bash")
        self.assertEqual(job.args, ["new.sh", "--flag"])
        self.assertEqual(job.cwd, "/home")

    def test_cannot_update_running_job(self):
        """Test that running job cannot be updated."""
        job = Job(1, "cmd", [], "/")
        job.start()

        with self.assertRaises(ValueError) as ctx:
            job.update("new_cmd", [], "/")
        self.assertIn("running", str(ctx.exception).lower())

    def test_can_update_completed_job(self):
        """Test that completed jobs can be updated."""
        job = Job(1, "cmd", [], "/")
        job.start()
        job.complete(0)

        # Should not raise
        job.update("new_cmd", ["arg"], "/new")
        self.assertEqual(job.command, "new_cmd")


class TestJobToDict(unittest.TestCase):
    """Test cases for job serialization."""

    def test_to_dict_pending_job(self):
        """Test converting pending job to dictionary."""
        job = Job(1, "python", ["test.py", "--verbose"], "/tmp/project")

        result = job.to_dict()

        self.assertEqual(result["id"], 1)
        self.assertEqual(result["command"], "python")
        self.assertEqual(result["args"], ["test.py", "--verbose"])
        self.assertEqual(result["cwd"], "/tmp/project")
        self.assertEqual(result["state"], STATE_PENDING)
        self.assertFalse(result["to_skip"])
        self.assertIsNone(result["exit_code"])
        self.assertEqual(result["log_file"], "job_001.log")
        self.assertIsNone(result["started_at"])
        self.assertIsNone(result["ended_at"])

    def test_to_dict_running_job(self):
        """Test converting running job to dictionary."""
        job = Job(2, "echo", ["hello"], "/")
        job.start()

        result = job.to_dict()

        self.assertEqual(result["state"], STATE_RUNNING)
        self.assertIsNotNone(result["started_at"])
        self.assertIsNone(result["ended_at"])
        self.assertIsNone(result["exit_code"])

    def test_to_dict_completed_job(self):
        """Test converting completed job to dictionary."""
        job = Job(3, "ls", ["-la"], "/tmp")
        job.start()
        job.complete(0)

        result = job.to_dict()

        self.assertEqual(result["state"], STATE_COMPLETED)
        self.assertEqual(result["exit_code"], 0)
        self.assertIsNotNone(result["started_at"])
        self.assertIsNotNone(result["ended_at"])

    def test_to_dict_skipped_job(self):
        """Test converting skipped job to dictionary."""
        job = Job(4, "cmd", [], "/", to_skip=True)

        result = job.to_dict()

        self.assertEqual(result["state"], STATE_SKIP)
        self.assertTrue(result["to_skip"])


class TestJobRepr(unittest.TestCase):
    """Test cases for job string representation."""

    def test_repr(self):
        """Test __repr__ method."""
        job = Job(42, "python", ["script.py"], "/tmp")

        repr_str = repr(job)

        self.assertIn("42", repr_str)
        self.assertIn("python", repr_str)
        self.assertIn(STATE_PENDING, repr_str)


if __name__ == "__main__":
    unittest.main()
