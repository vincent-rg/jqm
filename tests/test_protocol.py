"""Unit tests for the TCP/JSON protocol module."""

import json
import socket
import unittest
from unittest.mock import Mock, patch

from jqm.common.protocol import (
    ConnectionClosedError,
    ProtocolError,
    create_event,
    create_response,
    receive_message,
    send_message,
)


class TestSendMessage(unittest.TestCase):
    """Test cases for send_message function."""

    def test_send_simple_message(self):
        """Test sending a simple message."""
        mock_socket = Mock(spec=socket.socket)
        message = {"cmd": "list_jobs"}

        send_message(mock_socket, message)

        # Verify sendall was called once
        self.assertEqual(mock_socket.sendall.call_count, 1)

        # Get the sent data
        sent_data = mock_socket.sendall.call_args[0][0]

        # First 8 bytes should be length prefix
        length_prefix = sent_data[:8]
        length = int.from_bytes(length_prefix, byteorder="big")

        # Remaining bytes should be JSON
        json_bytes = sent_data[8:]
        self.assertEqual(len(json_bytes), length)

        # Decode and verify message
        decoded = json.loads(json_bytes.decode("utf-8"))
        self.assertEqual(decoded, message)

    def test_send_complex_message(self):
        """Test sending a message with nested data."""
        mock_socket = Mock(spec=socket.socket)
        message = {
            "cmd": "add_job",
            "data": {
                "command": "python",
                "args": ["script.py", "--verbose"],
                "cwd": "/path/to/dir",
            },
        }

        send_message(mock_socket, message)

        # Verify message was sent correctly
        sent_data = mock_socket.sendall.call_args[0][0]
        json_bytes = sent_data[8:]
        decoded = json.loads(json_bytes.decode("utf-8"))
        self.assertEqual(decoded, message)

    def test_send_message_connection_closed(self):
        """Test sending when connection is closed."""
        mock_socket = Mock(spec=socket.socket)
        mock_socket.sendall.side_effect = BrokenPipeError("Connection closed")

        message = {"cmd": "list_jobs"}

        with self.assertRaises(ConnectionClosedError):
            send_message(mock_socket, message)

    def test_send_message_invalid_json(self):
        """Test sending a message that cannot be JSON-encoded."""
        mock_socket = Mock(spec=socket.socket)

        # Create a non-serializable object
        class NonSerializable:
            pass

        message = {"data": NonSerializable()}

        with self.assertRaises(ProtocolError):
            send_message(mock_socket, message)


class TestReceiveMessage(unittest.TestCase):
    """Test cases for receive_message function."""

    def test_receive_simple_message(self):
        """Test receiving a simple message."""
        message = {"type": "response", "success": True}
        json_bytes = json.dumps(message).encode("utf-8")
        length = len(json_bytes)
        length_prefix = length.to_bytes(8, byteorder="big")

        mock_socket = Mock(spec=socket.socket)
        # recv will be called twice: once for length prefix, once for body
        mock_socket.recv.side_effect = [length_prefix, json_bytes]

        received = receive_message(mock_socket)
        self.assertEqual(received, message)

    def test_receive_message_in_chunks(self):
        """Test receiving a message in multiple chunks."""
        message = {"cmd": "list_jobs", "data": {"jobs": [1, 2, 3]}}
        json_bytes = json.dumps(message).encode("utf-8")
        length = len(json_bytes)
        length_prefix = length.to_bytes(8, byteorder="big")

        # Split both length prefix and body into small chunks
        mock_socket = Mock(spec=socket.socket)
        # Simulate receiving data in 5-byte chunks
        chunks = []

        # Split length prefix
        for i in range(0, len(length_prefix), 5):
            chunks.append(length_prefix[i : i + 5])

        # Split json body
        for i in range(0, len(json_bytes), 5):
            chunks.append(json_bytes[i : i + 5])

        mock_socket.recv.side_effect = chunks

        received = receive_message(mock_socket)
        self.assertEqual(received, message)

    def test_receive_message_connection_closed_at_length(self):
        """Test receiving when connection closes during length prefix."""
        mock_socket = Mock(spec=socket.socket)
        mock_socket.recv.return_value = b""  # Empty = connection closed

        with self.assertRaises(ConnectionClosedError):
            receive_message(mock_socket)

    def test_receive_message_connection_closed_at_body(self):
        """Test receiving when connection closes during message body."""
        length_prefix = (100).to_bytes(8, byteorder="big")

        mock_socket = Mock(spec=socket.socket)
        # First call returns length prefix, second returns empty (closed)
        mock_socket.recv.side_effect = [length_prefix, b""]

        with self.assertRaises(ConnectionClosedError):
            receive_message(mock_socket)

    def test_receive_message_invalid_length(self):
        """Test receiving message with invalid length prefix."""
        # Zero length
        length_prefix = (0).to_bytes(8, byteorder="big")
        mock_socket = Mock(spec=socket.socket)
        mock_socket.recv.return_value = length_prefix

        with self.assertRaises(ProtocolError):
            receive_message(mock_socket)

    def test_receive_message_invalid_json(self):
        """Test receiving invalid JSON data."""
        invalid_json = b"not valid json"
        length = len(invalid_json)
        length_prefix = length.to_bytes(8, byteorder="big")
        data = length_prefix + invalid_json

        mock_socket = Mock(spec=socket.socket)
        mock_socket.recv.return_value = data

        with self.assertRaises(ProtocolError):
            receive_message(mock_socket)


class TestCreateResponse(unittest.TestCase):
    """Test cases for create_response helper function."""

    def test_create_success_response_with_data(self):
        """Test creating a successful response with data."""
        response = create_response(success=True, data={"job_id": 42})

        self.assertEqual(response["type"], "response")
        self.assertTrue(response["success"])
        self.assertEqual(response["data"], {"job_id": 42})
        self.assertNotIn("error", response)

    def test_create_success_response_without_data(self):
        """Test creating a successful response without data."""
        response = create_response(success=True)

        self.assertEqual(response["type"], "response")
        self.assertTrue(response["success"])
        self.assertNotIn("data", response)
        self.assertNotIn("error", response)

    def test_create_error_response(self):
        """Test creating an error response."""
        response = create_response(success=False, error="Job not found")

        self.assertEqual(response["type"], "response")
        self.assertFalse(response["success"])
        self.assertEqual(response["error"], "Job not found")
        self.assertNotIn("data", response)

    def test_create_error_response_with_data(self):
        """Test creating an error response that also includes data."""
        response = create_response(
            success=False, data={"job_id": 42}, error="Cannot delete running job"
        )

        self.assertEqual(response["type"], "response")
        self.assertFalse(response["success"])
        self.assertEqual(response["data"], {"job_id": 42})
        self.assertEqual(response["error"], "Cannot delete running job")


class TestCreateEvent(unittest.TestCase):
    """Test cases for create_event helper function."""

    def test_create_event_simple(self):
        """Test creating a simple event."""
        event = create_event("job_added", {"job_id": 42})

        self.assertEqual(event["type"], "event")
        self.assertEqual(event["event"], "job_added")
        self.assertEqual(event["data"], {"job_id": 42})

    def test_create_event_complex_data(self):
        """Test creating an event with complex data."""
        event_data = {
            "job_id": 42,
            "old_state": "pending",
            "new_state": "running",
            "started_at": "2025-12-22T16:18:10",
        }
        event = create_event("job_status_changed", event_data)

        self.assertEqual(event["type"], "event")
        self.assertEqual(event["event"], "job_status_changed")
        self.assertEqual(event["data"], event_data)


class TestIntegration(unittest.TestCase):
    """Integration tests for send/receive cycle."""

    def test_send_receive_round_trip(self):
        """Test sending and receiving a message through real sockets."""
        # Create a pair of connected sockets
        server_sock, client_sock = socket.socketpair()

        try:
            # Send message from client
            message = {
                "cmd": "add_job",
                "data": {
                    "command": "python",
                    "args": ["test.py"],
                    "cwd": "/tmp",
                },
            }
            send_message(client_sock, message)

            # Receive on server
            received = receive_message(server_sock)

            # Verify
            self.assertEqual(received, message)

        finally:
            server_sock.close()
            client_sock.close()

    def test_multiple_messages(self):
        """Test sending and receiving multiple messages in sequence."""
        server_sock, client_sock = socket.socketpair()

        try:
            messages = [
                {"cmd": "list_jobs"},
                {"cmd": "get_queue_state"},
                {"cmd": "add_job", "data": {"command": "echo", "args": ["hello"]}},
            ]

            # Send all messages
            for msg in messages:
                send_message(client_sock, msg)

            # Receive all messages
            for expected in messages:
                received = receive_message(server_sock)
                self.assertEqual(received, expected)

        finally:
            server_sock.close()
            client_sock.close()


if __name__ == "__main__":
    unittest.main()
