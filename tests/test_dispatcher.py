"""Unit tests for the CommandDispatcher."""

import tempfile
import unittest
from pathlib import Path

from jqm.common.constants import STATE_PENDING, STATE_SKIP
from jqm.engine.dispatcher import CommandDispatcher
from jqm.engine.queue import JobQueue


class TestCommandDispatcher(unittest.TestCase):
    """Test cases for CommandDispatcher."""

    def setUp(self):
        """Set up test fixtures."""
        self.queue = JobQueue()
        self.temp_dir = tempfile.mkdtemp()
        self.dispatcher = CommandDispatcher(self.queue, self.temp_dir)

    def test_dispatch_unknown_command(self):
        """Test dispatching unknown command returns error."""
        response = self.dispatcher.dispatch({"cmd": "unknown_command"})

        self.assertFalse(response["success"])
        self.assertIn("Unknown command", response["error"])

    def test_dispatch_missing_cmd_field(self):
        """Test dispatching message without cmd field returns error."""
        response = self.dispatcher.dispatch({})

        self.assertFalse(response["success"])
        self.assertIn("Missing 'cmd' field", response["error"])

    def test_list_jobs_empty(self):
        """Test listing jobs when queue is empty."""
        response = self.dispatcher.dispatch({"cmd": "list_jobs"})

        self.assertTrue(response["success"])
        self.assertEqual(response["data"]["jobs"], [])

    def test_list_jobs_with_jobs(self):
        """Test listing jobs with multiple jobs in queue."""
        self.queue.add_job("cmd1", ["arg1"], "/tmp")
        self.queue.add_job("cmd2", ["arg2"], "/home")

        response = self.dispatcher.dispatch({"cmd": "list_jobs"})

        self.assertTrue(response["success"])
        jobs = response["data"]["jobs"]
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["command"], "cmd1")
        self.assertEqual(jobs[1]["command"], "cmd2")

    def test_add_job_success(self):
        """Test adding a job successfully."""
        message = {
            "cmd": "add_job",
            "data": {"command": "python", "args": ["script.py"], "cwd": "/tmp"},
        }

        response = self.dispatcher.dispatch(message)

        self.assertTrue(response["success"])
        self.assertEqual(response["data"]["job_id"], 1)
        self.assertEqual(len(self.queue.get_all_jobs()), 1)

    def test_add_job_missing_data(self):
        """Test adding job without data field returns error."""
        response = self.dispatcher.dispatch({"cmd": "add_job"})

        self.assertFalse(response["success"])
        self.assertIn("Missing 'data' field", response["error"])

    def test_add_job_missing_command(self):
        """Test adding job without command returns error."""
        message = {"cmd": "add_job", "data": {"args": [], "cwd": "/tmp"}}

        response = self.dispatcher.dispatch(message)

        self.assertFalse(response["success"])
        self.assertIn("Missing 'command'", response["error"])

    def test_add_job_missing_cwd(self):
        """Test adding job without cwd returns error."""
        message = {"cmd": "add_job", "data": {"command": "ls", "args": []}}

        response = self.dispatcher.dispatch(message)

        self.assertFalse(response["success"])
        self.assertIn("Missing 'cwd'", response["error"])

    def test_add_job_invalid_args_type(self):
        """Test adding job with non-list args returns error."""
        message = {
            "cmd": "add_job",
            "data": {"command": "ls", "args": "not_a_list", "cwd": "/tmp"},
        }

        response = self.dispatcher.dispatch(message)

        self.assertFalse(response["success"])
        self.assertIn("'args' must be a list", response["error"])

    def test_delete_job_success(self):
        """Test deleting a job successfully."""
        job_id = self.queue.add_job("cmd", [], "/tmp")

        response = self.dispatcher.dispatch({"cmd": "delete_job", "job_id": job_id})

        self.assertTrue(response["success"])
        self.assertEqual(len(self.queue.get_all_jobs()), 0)

    def test_delete_job_missing_id(self):
        """Test deleting job without job_id returns error."""
        response = self.dispatcher.dispatch({"cmd": "delete_job"})

        self.assertFalse(response["success"])
        self.assertIn("Missing 'job_id'", response["error"])

    def test_delete_job_not_found(self):
        """Test deleting non-existent job returns error."""
        response = self.dispatcher.dispatch({"cmd": "delete_job", "job_id": 999})

        self.assertFalse(response["success"])
        self.assertIn("not found", response["error"].lower())

    def test_update_job_success(self):
        """Test updating a job successfully."""
        job_id = self.queue.add_job("old_cmd", ["old_arg"], "/tmp")

        message = {
            "cmd": "update_job",
            "job_id": job_id,
            "data": {"command": "new_cmd", "args": ["new_arg"], "cwd": "/home"},
        }

        response = self.dispatcher.dispatch(message)

        self.assertTrue(response["success"])

        job = self.queue.get_job(job_id)
        self.assertEqual(job.command, "new_cmd")
        self.assertEqual(job.args, ["new_arg"])
        self.assertEqual(job.cwd, "/home")

    def test_update_job_missing_id(self):
        """Test updating job without job_id returns error."""
        message = {"cmd": "update_job", "data": {"command": "cmd", "args": [], "cwd": "/"}}

        response = self.dispatcher.dispatch(message)

        self.assertFalse(response["success"])
        self.assertIn("Missing 'job_id'", response["error"])

    def test_set_job_state_success(self):
        """Test setting job state successfully."""
        job_id = self.queue.add_job("cmd", [], "/tmp")

        response = self.dispatcher.dispatch(
            {"cmd": "set_job_state", "job_id": job_id, "state": STATE_SKIP}
        )

        self.assertTrue(response["success"])

        job = self.queue.get_job(job_id)
        self.assertEqual(job.state, STATE_SKIP)

    def test_set_job_state_missing_state(self):
        """Test setting job state without state field returns error."""
        job_id = self.queue.add_job("cmd", [], "/tmp")

        response = self.dispatcher.dispatch({"cmd": "set_job_state", "job_id": job_id})

        self.assertFalse(response["success"])
        self.assertIn("Missing 'state'", response["error"])

    def test_set_job_state_invalid_state(self):
        """Test setting job to invalid state returns error."""
        job_id = self.queue.add_job("cmd", [], "/tmp")

        response = self.dispatcher.dispatch(
            {"cmd": "set_job_state", "job_id": job_id, "state": "invalid"}
        )

        self.assertFalse(response["success"])
        self.assertIn("Invalid state", response["error"])

    def test_reorder_job_success(self):
        """Test reordering a job successfully."""
        job_id1 = self.queue.add_job("cmd1", [], "/tmp")
        job_id2 = self.queue.add_job("cmd2", [], "/tmp")

        response = self.dispatcher.dispatch(
            {"cmd": "reorder_job", "job_id": job_id2, "action": "up"}
        )

        self.assertTrue(response["success"])

        jobs = self.queue.get_all_jobs()
        self.assertEqual(jobs[0].id, job_id2)
        self.assertEqual(jobs[1].id, job_id1)

    def test_reorder_job_missing_action(self):
        """Test reordering job without action returns error."""
        job_id = self.queue.add_job("cmd", [], "/tmp")

        response = self.dispatcher.dispatch({"cmd": "reorder_job", "job_id": job_id})

        self.assertFalse(response["success"])
        self.assertIn("Missing 'action'", response["error"])

    def test_get_queue_state(self):
        """Test getting queue state."""
        self.queue.add_job("cmd", [], "/tmp")

        response = self.dispatcher.dispatch({"cmd": "get_queue_state"})

        self.assertTrue(response["success"])
        self.assertEqual(response["data"]["state"], "stopped")
        self.assertEqual(response["data"]["total_jobs"], 1)
        self.assertIsNone(response["data"]["current_job"])

    def test_set_queue_state_success(self):
        """Test setting queue state successfully."""
        response = self.dispatcher.dispatch({"cmd": "set_queue_state", "state": "started"})

        self.assertTrue(response["success"])
        self.assertTrue(self.queue.is_started())

    def test_set_queue_state_missing_state(self):
        """Test setting queue state without state field returns error."""
        response = self.dispatcher.dispatch({"cmd": "set_queue_state"})

        self.assertFalse(response["success"])
        self.assertIn("Missing 'state'", response["error"])

    def test_set_queue_state_invalid_state(self):
        """Test setting queue to invalid state returns error."""
        response = self.dispatcher.dispatch({"cmd": "set_queue_state", "state": "invalid"})

        self.assertFalse(response["success"])
        self.assertIn("Invalid queue state", response["error"])

    def test_get_job_log_not_started(self):
        """Test getting log for job that hasn't started returns empty log."""
        job_id = self.queue.add_job("cmd", [], "/tmp")

        response = self.dispatcher.dispatch({"cmd": "get_job_log", "job_id": job_id})

        self.assertTrue(response["success"])
        self.assertEqual(response["data"]["log"], "")

    def test_get_job_log_with_content(self):
        """Test getting log with content."""
        job_id = self.queue.add_job("cmd", [], "/tmp")
        job = self.queue.get_job(job_id)

        # Create a log file
        log_path = Path(self.temp_dir) / job.log_file
        log_content = "Test log content\nLine 2\n"
        log_path.write_text(log_content)

        response = self.dispatcher.dispatch({"cmd": "get_job_log", "job_id": job_id})

        self.assertTrue(response["success"])
        self.assertEqual(response["data"]["log"], log_content)

    def test_get_job_log_missing_id(self):
        """Test getting log without job_id returns error."""
        response = self.dispatcher.dispatch({"cmd": "get_job_log"})

        self.assertFalse(response["success"])
        self.assertIn("Missing 'job_id'", response["error"])

    def test_export_queue(self):
        """Test exporting queue returns XML."""
        response = self.dispatcher.dispatch({"cmd": "export_queue"})

        self.assertTrue(response["success"])
        self.assertIn("xml", response["data"])
        self.assertIn("<?xml", response["data"]["xml"])

    def test_import_queue_missing_xml(self):
        """Test importing without xml field returns error."""
        response = self.dispatcher.dispatch({"cmd": "import_queue", "mode": "replace"})

        self.assertFalse(response["success"])
        self.assertIn("Missing 'xml'", response["error"])

    def test_import_queue_invalid_mode(self):
        """Test importing with invalid mode returns error."""
        response = self.dispatcher.dispatch(
            {"cmd": "import_queue", "xml": "<queue/>", "mode": "invalid"}
        )

        self.assertFalse(response["success"])
        self.assertIn("'mode' must be", response["error"])


if __name__ == "__main__":
    unittest.main()
