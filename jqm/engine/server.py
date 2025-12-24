"""TCP server for the Engine.

Handles client connections and command dispatching.
"""

import logging
import socket
import threading
from pathlib import Path

from jqm.common.constants import DEFAULT_ENGINE_HOST, DEFAULT_ENGINE_PORT, DEFAULT_LOG_DIR
from jqm.common.protocol import (
    ConnectionClosedError,
    ProtocolError,
    create_response,
    receive_message,
    send_message,
)
from jqm.engine.dispatcher import CommandDispatcher
from jqm.engine.event_broadcaster import EventBroadcaster
from jqm.engine.executor import JobExecutor
from jqm.engine.queue import JobQueue

logger = logging.getLogger(__name__)


class EngineServer:
    """TCP server for the Engine.

    Listens for client connections and dispatches commands to the JobQueue.
    """

    def __init__(
        self,
        host: str = DEFAULT_ENGINE_HOST,
        port: int = DEFAULT_ENGINE_PORT,
        log_dir: str = DEFAULT_LOG_DIR,
    ):
        """Initialize the engine server.

        Args:
            host: Host to bind to (default: localhost)
            port: Port to listen on (default: 5051)
            log_dir: Directory for job log files (default: ./jqm_logs)
        """
        self.host = host
        self.port = port
        self.log_dir = log_dir

        # Create log directory if it doesn't exist
        Path(log_dir).mkdir(parents=True, exist_ok=True)

        self.queue = JobQueue()
        self.dispatcher = CommandDispatcher(self.queue, log_dir)
        self.broadcaster = EventBroadcaster()
        self.executor = JobExecutor(self.queue, self.broadcaster, log_dir)

        self._server_socket: socket.socket | None = None
        self._running = False
        self._server_thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the server in a background thread."""
        if self._running:
            logger.warning("Server is already running")
            return

        self._running = True

        # Start job executor
        self.executor.start()

        # Start TCP server
        self._server_thread = threading.Thread(target=self._run_server, daemon=True)
        self._server_thread.start()

        logger.info(f"Engine server started on {self.host}:{self.port}")

    def stop(self) -> None:
        """Stop the server and clean up resources."""
        if not self._running:
            return

        logger.info("Stopping engine server...")
        self._running = False

        # Stop job executor
        self.executor.stop()

        # Close server socket to unblock accept()
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception as e:
                logger.error(f"Error closing server socket: {e}")

        # Wait for server thread to finish
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=5)

        logger.info("Engine server stopped")

    def _run_server(self) -> None:
        """Main server loop (runs in background thread)."""
        try:
            # Create and configure server socket
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((self.host, self.port))
            self._server_socket.listen(5)

            logger.info(f"Listening for connections on {self.host}:{self.port}")

            while self._running:
                try:
                    client_socket, client_address = self._server_socket.accept()
                    logger.info(f"Client connected from {client_address}")

                    # Handle client in a separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket,),
                        daemon=True,
                    )
                    client_thread.start()

                except OSError as e:
                    if self._running:
                        logger.error(f"Error accepting connection: {e}")
                    break

        except Exception as e:
            logger.error(f"Server error: {e}", exc_info=True)
        finally:
            if self._server_socket:
                self._server_socket.close()

    def _handle_client(self, client_socket: socket.socket) -> None:
        """Handle a client connection.

        Args:
            client_socket: Client socket
        """
        subscribed = False

        try:
            while True:
                # Receive command from client
                try:
                    message = receive_message(client_socket)
                except ConnectionClosedError:
                    logger.info("Client disconnected")
                    break
                except ProtocolError as e:
                    logger.warning(f"Protocol error: {e}")
                    error_response = create_response(
                        success=False, error=f"Protocol error: {e}"
                    )
                    try:
                        send_message(client_socket, error_response)
                    except:
                        pass
                    break

                # Handle subscribe command specially
                cmd = message.get("cmd")
                if cmd == "subscribe":
                    self.broadcaster.subscribe(client_socket)
                    subscribed = True

                    # Send success response
                    response = create_response(success=True, data={})
                    send_message(client_socket, response)

                    logger.info("Client subscribed to events")

                    # Keep connection open for events
                    # Client will stay in this loop and receive events via broadcaster
                    continue

                # Dispatch command
                response = self.dispatcher.dispatch(message)

                # Send response
                try:
                    send_message(client_socket, response)
                except ConnectionClosedError:
                    logger.warning("Connection closed while sending response")
                    break

        except Exception as e:
            logger.error(f"Error handling client: {e}", exc_info=True)
        finally:
            # Clean up
            if subscribed:
                self.broadcaster.unsubscribe(client_socket)

            try:
                client_socket.close()
            except:
                pass

            logger.debug("Client connection closed")
