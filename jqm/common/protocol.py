"""TCP/JSON protocol implementation for JQM.

Protocol format: 8-byte length prefix (big-endian) + JSON payload
"""

import json
import logging
import socket
from typing import Any

from .constants import MESSAGE_ENCODING, MESSAGE_LENGTH_PREFIX_SIZE

logger = logging.getLogger(__name__)


class ProtocolError(Exception):
    """Raised when protocol-level errors occur."""
    pass


class ConnectionClosedError(ProtocolError):
    """Raised when connection is closed unexpectedly."""
    pass


def send_message(sock: socket.socket, message: dict[str, Any]) -> None:
    """Send a message over a socket using the JQM protocol.

    Args:
        sock: Socket to send the message on
        message: Dictionary to send as JSON

    Raises:
        ProtocolError: If message cannot be encoded or sent
        ConnectionClosedError: If connection is closed during send
    """
    try:
        # Encode message as JSON
        json_data = json.dumps(message)
        json_bytes = json_data.encode(MESSAGE_ENCODING)

        # Create length prefix (8 bytes, big-endian)
        length = len(json_bytes)
        length_prefix = length.to_bytes(MESSAGE_LENGTH_PREFIX_SIZE, byteorder="big")

        # Send length prefix + JSON data
        data = length_prefix + json_bytes
        sock.sendall(data)

        logger.debug(f"Sent message: {message}")

    except TypeError as e:
        raise ProtocolError(f"Failed to encode message as JSON: {e}")
    except (BrokenPipeError, ConnectionResetError, OSError) as e:
        raise ConnectionClosedError(f"Connection closed during send: {e}")


def receive_message(sock: socket.socket) -> dict[str, Any]:
    """Receive a message from a socket using the JQM protocol.

    Args:
        sock: Socket to receive the message from

    Returns:
        Decoded message as a dictionary

    Raises:
        ProtocolError: If message cannot be decoded
        ConnectionClosedError: If connection is closed during receive
    """
    try:
        # Read length prefix (8 bytes)
        length_prefix = _receive_exact(sock, MESSAGE_LENGTH_PREFIX_SIZE)
        if not length_prefix:
            raise ConnectionClosedError("Connection closed while reading length prefix")

        # Decode length
        length = int.from_bytes(length_prefix, byteorder="big")

        # Validate length (sanity check: max 10MB)
        if length <= 0 or length > 10 * 1024 * 1024:
            raise ProtocolError(f"Invalid message length: {length}")

        # Read JSON data
        json_bytes = _receive_exact(sock, length)
        if not json_bytes:
            raise ConnectionClosedError("Connection closed while reading message body")

        # Decode JSON
        json_data = json_bytes.decode(MESSAGE_ENCODING)
        message = json.loads(json_data)

        logger.debug(f"Received message: {message}")
        return message

    except json.JSONDecodeError as e:
        raise ProtocolError(f"Failed to decode message as JSON: {e}")
    except UnicodeDecodeError as e:
        raise ProtocolError(f"Failed to decode message bytes: {e}")


def _receive_exact(sock: socket.socket, num_bytes: int) -> bytes:
    """Receive exactly num_bytes from socket.

    Args:
        sock: Socket to receive from
        num_bytes: Number of bytes to receive

    Returns:
        Received bytes (exactly num_bytes)

    Raises:
        ConnectionClosedError: If connection is closed before receiving all bytes
    """
    data = b""
    while len(data) < num_bytes:
        try:
            chunk = sock.recv(num_bytes - len(data))
            if not chunk:
                # Connection closed
                if data:
                    raise ConnectionClosedError(
                        f"Connection closed after receiving {len(data)}/{num_bytes} bytes"
                    )
                return b""
            data += chunk
        except (ConnectionResetError, OSError) as e:
            raise ConnectionClosedError(f"Connection error during receive: {e}")

    return data


def create_response(success: bool, data: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any]:
    """Create a standard response message.

    Args:
        success: Whether the operation succeeded
        data: Optional data payload
        error: Optional error message (used when success=False)

    Returns:
        Response message dictionary
    """
    response = {
        "type": "response",
        "success": success,
    }

    if data is not None:
        response["data"] = data

    if error is not None:
        response["error"] = error

    return response


def create_event(event_name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Create a standard event message.

    Args:
        event_name: Name of the event
        data: Event payload

    Returns:
        Event message dictionary
    """
    return {
        "type": "event",
        "event": event_name,
        "data": data,
    }
