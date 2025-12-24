"""Integration tests for the Engine TCP server."""

import socket
import tempfile
import time
import unittest

from jqm.common.protocol import receive_message, send_message
from jqm.engine.server import EngineServer


class TestEngineServerIntegration(unittest.TestCase):
    """Integration tests for EngineServer."""

    @classmethod
    def setUpClass(cls):
        """Set up test server (once for all tests)."""
        cls.temp_dir = tempfile.mkdtemp()
        cls.server = EngineServer(host="127.0.0.1", port=0, log_dir=cls.temp_dir)  # port=0 for random port

        # Start server
        cls.server.start()

        # Get the actual port assigned
        time.sleep(0.1)  # Give server time to start
        cls.port = cls.server._server_socket.getsockname()[1]

    @classmethod
    def tearDownClass(cls):
        """Tear down test server."""
        cls.server.stop()

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
            # Can only delete non-running jobs
            if job["state"] != "running":
                send_message(self.client, {"cmd": "delete_job", "job_id": job["id"]})
                receive_message(self.client)  # consume response

    def tearDown(self):
        """Clean up client connection."""
        self.client.close()

    def test_list_jobs_empty(self):
        """Test listing jobs when queue is empty."""
        send_message(self.client, {"cmd": "list_jobs"})
        response = receive_message(self.client)

        self.assertTrue(response["success"])
        self.assertEqual(response["data"]["jobs"], [])

    def test_add_and_list_job(self):
        """Test adding a job and then listing it."""
        # Add job
        add_message = {
            "cmd": "add_job",
            "data": {"command": "python", "args": ["script.py"], "cwd": "/tmp"},
        }
        send_message(self.client, add_message)
        add_response = receive_message(self.client)

        self.assertTrue(add_response["success"])
        job_id = add_response["data"]["job_id"]

        # List jobs
        send_message(self.client, {"cmd": "list_jobs"})
        list_response = receive_message(self.client)

        self.assertTrue(list_response["success"])
        jobs = list_response["data"]["jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], job_id)
        self.assertEqual(jobs[0]["command"], "python")

    def test_get_queue_state(self):
        """Test getting queue state."""
        send_message(self.client, {"cmd": "get_queue_state"})
        response = receive_message(self.client)

        self.assertTrue(response["success"])
        self.assertIn("state", response["data"])
        self.assertIn("total_jobs", response["data"])

    def test_set_queue_state(self):
        """Test setting queue state."""
        send_message(self.client, {"cmd": "set_queue_state", "state": "started"})
        response = receive_message(self.client)

        self.assertTrue(response["success"])

        # Verify state changed
        send_message(self.client, {"cmd": "get_queue_state"})
        state_response = receive_message(self.client)

        self.assertEqual(state_response["data"]["state"], "started")

        # Reset to stopped
        send_message(self.client, {"cmd": "set_queue_state", "state": "stopped"})
        receive_message(self.client)

    def test_delete_job(self):
        """Test deleting a job."""
        # Add a job first
        add_message = {
            "cmd": "add_job",
            "data": {"command": "echo", "args": ["hello"], "cwd": "/"},
        }
        send_message(self.client, add_message)
        add_response = receive_message(self.client)
        job_id = add_response["data"]["job_id"]

        # Delete it
        send_message(self.client, {"cmd": "delete_job", "job_id": job_id})
        delete_response = receive_message(self.client)

        self.assertTrue(delete_response["success"])

        # Verify it's gone
        send_message(self.client, {"cmd": "list_jobs"})
        list_response = receive_message(self.client)

        jobs = [j for j in list_response["data"]["jobs"] if j["id"] == job_id]
        self.assertEqual(len(jobs), 0)

    def test_update_job(self):
        """Test updating a job."""
        # Add a job
        add_message = {
            "cmd": "add_job",
            "data": {"command": "old_cmd", "args": [], "cwd": "/tmp"},
        }
        send_message(self.client, add_message)
        add_response = receive_message(self.client)
        job_id = add_response["data"]["job_id"]

        # Update it
        update_message = {
            "cmd": "update_job",
            "job_id": job_id,
            "data": {"command": "new_cmd", "args": ["arg"], "cwd": "/home"},
        }
        send_message(self.client, update_message)
        update_response = receive_message(self.client)

        self.assertTrue(update_response["success"])

        # Verify update
        send_message(self.client, {"cmd": "list_jobs"})
        list_response = receive_message(self.client)

        job = next(j for j in list_response["data"]["jobs"] if j["id"] == job_id)
        self.assertEqual(job["command"], "new_cmd")
        self.assertEqual(job["args"], ["arg"])
        self.assertEqual(job["cwd"], "/home")

    def test_set_job_state(self):
        """Test setting job state."""
        # Add a job
        add_message = {
            "cmd": "add_job",
            "data": {"command": "cmd", "args": [], "cwd": "/"},
        }
        send_message(self.client, add_message)
        add_response = receive_message(self.client)
        job_id = add_response["data"]["job_id"]

        # Set to skip
        send_message(self.client, {"cmd": "set_job_state", "job_id": job_id, "state": "skip"})
        response = receive_message(self.client)

        self.assertTrue(response["success"])

        # Verify state changed
        send_message(self.client, {"cmd": "list_jobs"})
        list_response = receive_message(self.client)

        job = next(j for j in list_response["data"]["jobs"] if j["id"] == job_id)
        self.assertEqual(job["state"], "skip")
        self.assertTrue(job["to_skip"])

    def test_reorder_job(self):
        """Test reordering jobs."""
        # Add two jobs
        send_message(self.client, {
            "cmd": "add_job",
            "data": {"command": "cmd1", "args": [], "cwd": "/"},
        })
        job1_id = receive_message(self.client)["data"]["job_id"]

        send_message(self.client, {
            "cmd": "add_job",
            "data": {"command": "cmd2", "args": [], "cwd": "/"},
        })
        job2_id = receive_message(self.client)["data"]["job_id"]

        # Move job2 to top
        send_message(self.client, {"cmd": "reorder_job", "job_id": job2_id, "action": "top"})
        response = receive_message(self.client)

        self.assertTrue(response["success"])

        # Verify order
        send_message(self.client, {"cmd": "list_jobs"})
        list_response = receive_message(self.client)

        jobs = list_response["data"]["jobs"]
        self.assertEqual(jobs[0]["id"], job2_id)
        self.assertEqual(jobs[1]["id"], job1_id)

    def test_get_job_log(self):
        """Test getting job log."""
        # Add a job
        send_message(self.client, {
            "cmd": "add_job",
            "data": {"command": "cmd", "args": [], "cwd": "/"},
        })
        job_id = receive_message(self.client)["data"]["job_id"]

        # Get log (should be empty since job hasn't run)
        send_message(self.client, {"cmd": "get_job_log", "job_id": job_id})
        response = receive_message(self.client)

        self.assertTrue(response["success"])
        self.assertEqual(response["data"]["log"], "")

    def test_error_handling_invalid_command(self):
        """Test error handling for invalid command."""
        send_message(self.client, {"cmd": "invalid_command"})
        response = receive_message(self.client)

        self.assertFalse(response["success"])
        self.assertIn("Unknown command", response["error"])

    def test_error_handling_job_not_found(self):
        """Test error handling for non-existent job."""
        send_message(self.client, {"cmd": "delete_job", "job_id": 99999})
        response = receive_message(self.client)

        self.assertFalse(response["success"])
        self.assertIn("not found", response["error"].lower())

    def test_multiple_sequential_commands(self):
        """Test multiple commands in sequence on same connection."""
        # Add job
        send_message(self.client, {
            "cmd": "add_job",
            "data": {"command": "cmd1", "args": [], "cwd": "/"},
        })
        response1 = receive_message(self.client)
        self.assertTrue(response1["success"])

        # Add another
        send_message(self.client, {
            "cmd": "add_job",
            "data": {"command": "cmd2", "args": [], "cwd": "/"},
        })
        response2 = receive_message(self.client)
        self.assertTrue(response2["success"])

        # List them
        send_message(self.client, {"cmd": "list_jobs"})
        response3 = receive_message(self.client)
        self.assertTrue(response3["success"])
        self.assertEqual(len(response3["data"]["jobs"]), 2)


if __name__ == "__main__":
    unittest.main()
