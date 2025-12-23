"""Unit tests for the JobQueue class."""

import unittest

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
from jqm.engine.queue import InvalidOperationError, JobNotFoundError, JobQueue


class TestQueueInitialization(unittest.TestCase):
    """Test cases for JobQueue initialization."""

    def test_create_empty_queue(self):
        """Test creating an empty queue."""
        queue = JobQueue()

        self.assertEqual(queue.get_state(), QUEUE_STATE_STOPPED)
        self.assertEqual(len(queue.get_all_jobs()), 0)
        self.assertEqual(queue._next_job_id, 1)

    def test_initial_state_is_stopped(self):
        """Test that initial queue state is stopped."""
        queue = JobQueue()

        self.assertTrue(queue.is_stopped())
        self.assertFalse(queue.is_started())
        self.assertFalse(queue.is_paused())


class TestQueueStateManagement(unittest.TestCase):
    """Test cases for queue state management."""

    def test_set_state_to_started(self):
        """Test setting queue state to started."""
        queue = JobQueue()

        queue.set_state(QUEUE_STATE_STARTED)

        self.assertEqual(queue.get_state(), QUEUE_STATE_STARTED)
        self.assertTrue(queue.is_started())

    def test_set_state_to_paused(self):
        """Test setting queue state to paused."""
        queue = JobQueue()

        queue.set_state(QUEUE_STATE_PAUSED)

        self.assertEqual(queue.get_state(), QUEUE_STATE_PAUSED)
        self.assertTrue(queue.is_paused())

    def test_set_state_to_stopped(self):
        """Test setting queue state back to stopped."""
        queue = JobQueue()
        queue.set_state(QUEUE_STATE_STARTED)

        queue.set_state(QUEUE_STATE_STOPPED)

        self.assertTrue(queue.is_stopped())

    def test_set_invalid_state_raises_error(self):
        """Test that setting invalid state raises ValueError."""
        queue = JobQueue()

        with self.assertRaises(ValueError) as ctx:
            queue.set_state("invalid_state")
        self.assertIn("invalid", str(ctx.exception).lower())


class TestAddJob(unittest.TestCase):
    """Test cases for adding jobs to queue."""

    def test_add_single_job(self):
        """Test adding a single job."""
        queue = JobQueue()

        job_id = queue.add_job("python", ["script.py"], "/tmp")

        self.assertEqual(job_id, 1)
        self.assertEqual(len(queue.get_all_jobs()), 1)

    def test_add_multiple_jobs(self):
        """Test adding multiple jobs."""
        queue = JobQueue()

        id1 = queue.add_job("cmd1", [], "/")
        id2 = queue.add_job("cmd2", [], "/")
        id3 = queue.add_job("cmd3", [], "/")

        self.assertEqual(id1, 1)
        self.assertEqual(id2, 2)
        self.assertEqual(id3, 3)
        self.assertEqual(len(queue.get_all_jobs()), 3)

    def test_job_ids_auto_increment(self):
        """Test that job IDs auto-increment correctly."""
        queue = JobQueue()

        ids = [queue.add_job("cmd", [], "/") for _ in range(5)]

        self.assertEqual(ids, [1, 2, 3, 4, 5])


class TestGetJob(unittest.TestCase):
    """Test cases for retrieving jobs."""

    def test_get_existing_job(self):
        """Test getting a job by ID."""
        queue = JobQueue()
        job_id = queue.add_job("python", ["test.py"], "/tmp")

        job = queue.get_job(job_id)

        self.assertEqual(job.id, job_id)
        self.assertEqual(job.command, "python")

    def test_get_nonexistent_job_raises_error(self):
        """Test that getting non-existent job raises JobNotFoundError."""
        queue = JobQueue()

        with self.assertRaises(JobNotFoundError):
            queue.get_job(999)

    def test_get_all_jobs(self):
        """Test getting all jobs."""
        queue = JobQueue()
        queue.add_job("cmd1", [], "/")
        queue.add_job("cmd2", [], "/")

        jobs = queue.get_all_jobs()

        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0].command, "cmd1")
        self.assertEqual(jobs[1].command, "cmd2")

    def test_get_all_jobs_returns_copy(self):
        """Test that get_all_jobs returns a copy, not reference."""
        queue = JobQueue()
        queue.add_job("cmd", [], "/")

        jobs = queue.get_all_jobs()
        jobs.clear()

        # Original queue should still have the job
        self.assertEqual(len(queue.get_all_jobs()), 1)


class TestDeleteJob(unittest.TestCase):
    """Test cases for deleting jobs."""

    def test_delete_job_when_stopped(self):
        """Test deleting a job when queue is stopped."""
        queue = JobQueue()
        job_id = queue.add_job("cmd", [], "/")

        queue.delete_job(job_id)

        self.assertEqual(len(queue.get_all_jobs()), 0)

    def test_delete_nonexistent_job_raises_error(self):
        """Test that deleting non-existent job raises error."""
        queue = JobQueue()

        with self.assertRaises(JobNotFoundError):
            queue.delete_job(999)

    def test_cannot_delete_running_job(self):
        """Test that running job cannot be deleted."""
        queue = JobQueue()
        job_id = queue.add_job("cmd", [], "/")

        job = queue.get_job(job_id)
        job.start()

        with self.assertRaises(InvalidOperationError) as ctx:
            queue.delete_job(job_id)
        self.assertIn("running", str(ctx.exception).lower())

    def test_cannot_delete_job_before_running_when_started(self):
        """Test that jobs before running job cannot be deleted when queue is started."""
        queue = JobQueue()
        id1 = queue.add_job("cmd1", [], "/")
        id2 = queue.add_job("cmd2", [], "/")
        id3 = queue.add_job("cmd3", [], "/")

        # Start second job
        job2 = queue.get_job(id2)
        job2.start()

        queue.set_state(QUEUE_STATE_STARTED)

        # Cannot delete job before running job
        with self.assertRaises(InvalidOperationError):
            queue.delete_job(id1)

        # Can delete job after running job
        queue.delete_job(id3)  # Should not raise

    def test_can_delete_job_after_running_when_started(self):
        """Test that jobs after running job can be deleted when queue is started."""
        queue = JobQueue()
        id1 = queue.add_job("cmd1", [], "/")
        id2 = queue.add_job("cmd2", [], "/")

        job1 = queue.get_job(id1)
        job1.start()

        queue.set_state(QUEUE_STATE_STARTED)

        # Should be able to delete job2 (after running job)
        queue.delete_job(id2)

        self.assertEqual(len(queue.get_all_jobs()), 1)


class TestUpdateJob(unittest.TestCase):
    """Test cases for updating jobs."""

    def test_update_job_when_stopped(self):
        """Test updating a job when queue is stopped."""
        queue = JobQueue()
        job_id = queue.add_job("old_cmd", ["old_arg"], "/old")

        queue.update_job(job_id, "new_cmd", ["new_arg"], "/new")

        job = queue.get_job(job_id)
        self.assertEqual(job.command, "new_cmd")
        self.assertEqual(job.args, ["new_arg"])
        self.assertEqual(job.cwd, "/new")

    def test_cannot_update_running_job(self):
        """Test that running job cannot be updated."""
        queue = JobQueue()
        job_id = queue.add_job("cmd", [], "/")

        job = queue.get_job(job_id)
        job.start()

        with self.assertRaises(InvalidOperationError):
            queue.update_job(job_id, "new", [], "/")

    def test_cannot_update_job_before_running_when_started(self):
        """Test that jobs before running job cannot be updated when started."""
        queue = JobQueue()
        id1 = queue.add_job("cmd1", [], "/")
        id2 = queue.add_job("cmd2", [], "/")

        job2 = queue.get_job(id2)
        job2.start()

        queue.set_state(QUEUE_STATE_STARTED)

        with self.assertRaises(InvalidOperationError):
            queue.update_job(id1, "new", [], "/")


class TestSetJobState(unittest.TestCase):
    """Test cases for setting job state."""

    def test_set_job_to_skip(self):
        """Test setting a job to skip state."""
        queue = JobQueue()
        job_id = queue.add_job("cmd", [], "/")

        queue.set_job_state(job_id, STATE_SKIP)

        job = queue.get_job(job_id)
        self.assertTrue(job.is_skipped())
        self.assertTrue(job.to_skip)

    def test_set_job_to_pending(self):
        """Test setting a job to pending state."""
        queue = JobQueue()
        job_id = queue.add_job("cmd", [], "/")
        queue.set_job_state(job_id, STATE_SKIP)

        queue.set_job_state(job_id, STATE_PENDING)

        job = queue.get_job(job_id)
        self.assertTrue(job.is_pending())
        self.assertFalse(job.to_skip)

    def test_cannot_set_state_of_running_job(self):
        """Test that running job state cannot be changed."""
        queue = JobQueue()
        job_id = queue.add_job("cmd", [], "/")
        job = queue.get_job(job_id)
        job.start()

        with self.assertRaises(InvalidOperationError):
            queue.set_job_state(job_id, STATE_SKIP)

    def test_invalid_state_raises_error(self):
        """Test that setting invalid state raises ValueError."""
        queue = JobQueue()
        job_id = queue.add_job("cmd", [], "/")

        with self.assertRaises(ValueError):
            queue.set_job_state(job_id, "invalid_state")


class TestReorderJob(unittest.TestCase):
    """Test cases for reordering jobs."""

    def setUp(self):
        """Set up test queue with multiple jobs."""
        self.queue = JobQueue()
        self.ids = [self.queue.add_job(f"cmd{i}", [], "/") for i in range(5)]

    def test_reorder_to_top(self):
        """Test moving a job to top."""
        self.queue.reorder_job(self.ids[3], REORDER_TOP)

        jobs = self.queue.get_all_jobs()
        self.assertEqual(jobs[0].id, self.ids[3])

    def test_reorder_to_bottom(self):
        """Test moving a job to bottom."""
        self.queue.reorder_job(self.ids[1], REORDER_BOTTOM)

        jobs = self.queue.get_all_jobs()
        self.assertEqual(jobs[-1].id, self.ids[1])

    def test_reorder_up(self):
        """Test moving a job up one position."""
        self.queue.reorder_job(self.ids[2], REORDER_UP)

        jobs = self.queue.get_all_jobs()
        self.assertEqual(jobs[1].id, self.ids[2])

    def test_reorder_down(self):
        """Test moving a job down one position."""
        self.queue.reorder_job(self.ids[2], REORDER_DOWN)

        jobs = self.queue.get_all_jobs()
        self.assertEqual(jobs[3].id, self.ids[2])

    def test_reorder_up_at_top_stays_at_top(self):
        """Test that moving top job up keeps it at top."""
        self.queue.reorder_job(self.ids[0], REORDER_UP)

        jobs = self.queue.get_all_jobs()
        self.assertEqual(jobs[0].id, self.ids[0])

    def test_reorder_down_at_bottom_stays_at_bottom(self):
        """Test that moving bottom job down keeps it at bottom."""
        self.queue.reorder_job(self.ids[4], REORDER_DOWN)

        jobs = self.queue.get_all_jobs()
        self.assertEqual(jobs[-1].id, self.ids[4])

    def test_cannot_reorder_running_job(self):
        """Test that running job cannot be reordered."""
        job = self.queue.get_job(self.ids[2])
        job.start()

        with self.assertRaises(InvalidOperationError):
            self.queue.reorder_job(self.ids[2], REORDER_TOP)

    def test_cannot_reorder_job_before_running_when_started(self):
        """Test that jobs before running job cannot be reordered when started."""
        job = self.queue.get_job(self.ids[2])
        job.start()

        self.queue.set_state(QUEUE_STATE_STARTED)

        with self.assertRaises(InvalidOperationError):
            self.queue.reorder_job(self.ids[1], REORDER_UP)

    def test_can_reorder_jobs_after_running_when_started(self):
        """Test that jobs after running job can be reordered when started."""
        job = self.queue.get_job(self.ids[1])
        job.start()

        self.queue.set_state(QUEUE_STATE_STARTED)

        # Move job 3 to top (which should be position after running job)
        self.queue.reorder_job(self.ids[3], REORDER_TOP)

        jobs = self.queue.get_all_jobs()
        # Job should be at index 2 (after running job at index 1)
        self.assertEqual(jobs[2].id, self.ids[3])

    def test_invalid_reorder_action_raises_error(self):
        """Test that invalid reorder action raises ValueError."""
        with self.assertRaises(ValueError):
            self.queue.reorder_job(self.ids[0], "invalid_action")


class TestGetRunningJob(unittest.TestCase):
    """Test cases for getting running job."""

    def test_no_running_job_returns_none(self):
        """Test that get_running_job returns None when no job is running."""
        queue = JobQueue()
        queue.add_job("cmd", [], "/")

        running = queue.get_running_job()

        self.assertIsNone(running)

    def test_get_running_job(self):
        """Test getting the running job."""
        queue = JobQueue()
        id1 = queue.add_job("cmd1", [], "/")
        id2 = queue.add_job("cmd2", [], "/")

        job1 = queue.get_job(id1)
        job1.start()

        running = queue.get_running_job()

        self.assertIsNotNone(running)
        self.assertEqual(running.id, id1)


class TestGetNextExecutableJob(unittest.TestCase):
    """Test cases for getting next executable job."""

    def test_get_next_executable_job_from_start(self):
        """Test getting next job when no job is running."""
        queue = JobQueue()
        queue.add_job("cmd1", [], "/")
        queue.add_job("cmd2", [], "/")

        next_job = queue.get_next_executable_job()

        self.assertIsNotNone(next_job)
        self.assertEqual(next_job.command, "cmd1")

    def test_get_next_executable_job_after_running(self):
        """Test getting next job after running job."""
        queue = JobQueue()
        id1 = queue.add_job("cmd1", [], "/")
        queue.add_job("cmd2", [], "/")

        job1 = queue.get_job(id1)
        job1.start()

        next_job = queue.get_next_executable_job()

        self.assertIsNotNone(next_job)
        self.assertEqual(next_job.command, "cmd2")

    def test_get_next_executable_job_skips_skipped_jobs(self):
        """Test that get_next_executable_job skips jobs marked to skip."""
        queue = JobQueue()
        id1 = queue.add_job("cmd1", [], "/")
        id2 = queue.add_job("cmd2", [], "/")
        id3 = queue.add_job("cmd3", [], "/")

        # Skip job 2
        queue.set_job_state(id2, STATE_SKIP)

        job1 = queue.get_job(id1)
        job1.start()

        next_job = queue.get_next_executable_job()

        # Should get job3, not job2
        self.assertIsNotNone(next_job)
        self.assertEqual(next_job.command, "cmd3")

    def test_get_next_executable_job_returns_none_when_all_done(self):
        """Test that None is returned when all jobs are done."""
        queue = JobQueue()
        id1 = queue.add_job("cmd1", [], "/")

        job1 = queue.get_job(id1)
        job1.start()
        job1.complete(0)

        next_job = queue.get_next_executable_job()

        self.assertIsNone(next_job)

    def test_get_next_executable_job_returns_none_when_empty(self):
        """Test that None is returned for empty queue."""
        queue = JobQueue()

        next_job = queue.get_next_executable_job()

        self.assertIsNone(next_job)


class TestGetQueueInfo(unittest.TestCase):
    """Test cases for getting queue information."""

    def test_get_queue_info_empty(self):
        """Test getting info for empty queue."""
        queue = JobQueue()

        info = queue.get_queue_info()

        self.assertEqual(info["state"], QUEUE_STATE_STOPPED)
        self.assertEqual(info["total_jobs"], 0)
        self.assertIsNone(info["current_job"])
        self.assertIsNone(info["current_job_started_at"])

    def test_get_queue_info_with_pending_jobs(self):
        """Test getting info with pending jobs."""
        queue = JobQueue()
        queue.add_job("cmd1", [], "/")
        queue.add_job("cmd2", [], "/")

        info = queue.get_queue_info()

        self.assertEqual(info["total_jobs"], 2)
        self.assertIsNone(info["current_job"])

    def test_get_queue_info_with_running_job(self):
        """Test getting info with running job."""
        queue = JobQueue()
        queue.add_job("cmd1", [], "/")
        id2 = queue.add_job("cmd2", [], "/")
        queue.add_job("cmd3", [], "/")

        job2 = queue.get_job(id2)
        job2.start()

        queue.set_state(QUEUE_STATE_STARTED)

        info = queue.get_queue_info()

        self.assertEqual(info["state"], QUEUE_STATE_STARTED)
        self.assertEqual(info["total_jobs"], 3)
        self.assertEqual(info["current_job"], 2)  # Second job (1-indexed)
        self.assertIsNotNone(info["current_job_started_at"])


if __name__ == "__main__":
    unittest.main()
