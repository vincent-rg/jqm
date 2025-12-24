"""Event broadcasting system for Engine.

Manages subscribed clients and broadcasts events to them.
"""

import logging
import socket
import threading
from typing import Any

from jqm.common.protocol import ConnectionClosedError, create_event, send_message

logger = logging.getLogger(__name__)


class EventBroadcaster:
    """Manages event subscriptions and broadcasting.

    Thread-safe broadcaster that sends events to all subscribed clients.
    """

    def __init__(self):
        """Initialize the event broadcaster."""
        self._subscribers: list[socket.socket] = []
        self._lock = threading.Lock()

    def subscribe(self, client_socket: socket.socket) -> None:
        """Add a client to the subscriber list.

        Args:
            client_socket: Socket to receive events
        """
        with self._lock:
            if client_socket not in self._subscribers:
                self._subscribers.append(client_socket)
                logger.info(f"Client subscribed (total subscribers: {len(self._subscribers)})")

    def unsubscribe(self, client_socket: socket.socket) -> None:
        """Remove a client from the subscriber list.

        Args:
            client_socket: Socket to stop receiving events
        """
        with self._lock:
            if client_socket in self._subscribers:
                self._subscribers.remove(client_socket)
                logger.info(f"Client unsubscribed (total subscribers: {len(self._subscribers)})")

    def broadcast_event(self, event_name: str, data: dict[str, Any]) -> None:
        """Broadcast an event to all subscribed clients.

        Args:
            event_name: Name of the event (e.g., "job_added")
            data: Event payload
        """
        event_message = create_event(event_name, data)

        with self._lock:
            # Copy subscriber list to avoid holding lock during sends
            subscribers = self._subscribers.copy()

        if not subscribers:
            return

        logger.debug(f"Broadcasting event '{event_name}' to {len(subscribers)} subscribers")

        # Send to all subscribers (outside the lock)
        disconnected = []
        for client_socket in subscribers:
            try:
                send_message(client_socket, event_message)
            except (ConnectionClosedError, OSError) as e:
                logger.warning(f"Failed to send event to subscriber: {e}")
                disconnected.append(client_socket)

        # Remove disconnected clients
        if disconnected:
            with self._lock:
                for client_socket in disconnected:
                    if client_socket in self._subscribers:
                        self._subscribers.remove(client_socket)
                        logger.info(f"Removed disconnected subscriber (total: {len(self._subscribers)})")

    def broadcast_job_added(self, job_dict: dict[str, Any]) -> None:
        """Broadcast job_added event.

        Args:
            job_dict: Job data dictionary from job.to_dict()
        """
        self.broadcast_event("job_added", job_dict)

    def broadcast_job_removed(self, job_id: int) -> None:
        """Broadcast job_removed event.

        Args:
            job_id: ID of removed job
        """
        self.broadcast_event("job_removed", {"job_id": job_id})

    def broadcast_job_status_changed(
        self, job_id: int, old_state: str, new_state: str, started_at: str | None = None
    ) -> None:
        """Broadcast job_status_changed event.

        Args:
            job_id: ID of the job
            old_state: Previous state
            new_state: New state
            started_at: ISO timestamp when job started (optional)
        """
        data = {
            "job_id": job_id,
            "old_state": old_state,
            "new_state": new_state,
        }
        if started_at:
            data["started_at"] = started_at

        self.broadcast_event("job_status_changed", data)

    def broadcast_job_updated(self, job_dict: dict[str, Any]) -> None:
        """Broadcast job_updated event.

        Args:
            job_dict: Updated job data dictionary from job.to_dict()
        """
        self.broadcast_event("job_updated", job_dict)

    def broadcast_queue_state_changed(self, state: str, current_job: int | None, total_jobs: int) -> None:
        """Broadcast queue_state_changed event.

        Args:
            state: New queue state
            current_job: Position of current job (1-indexed, None if no job running)
            total_jobs: Total number of jobs in queue
        """
        data = {
            "state": state,
            "current_job": current_job,
            "total_jobs": total_jobs,
        }
        self.broadcast_event("queue_state_changed", data)

    def broadcast_queue_progress(
        self,
        current_job: int,
        total_jobs: int,
        job_id: int,
        command: str,
        started_at: str,
    ) -> None:
        """Broadcast queue_progress event.

        Args:
            current_job: Position of current job (1-indexed)
            total_jobs: Total number of jobs
            job_id: ID of the job that just started
            command: Command of the job
            started_at: ISO timestamp when job started
        """
        data = {
            "current_job": current_job,
            "total_jobs": total_jobs,
            "job_id": job_id,
            "command": command,
            "started_at": started_at,
        }
        self.broadcast_event("queue_progress", data)

    def get_subscriber_count(self) -> int:
        """Get the number of subscribed clients.

        Returns:
            Number of subscribers
        """
        with self._lock:
            return len(self._subscribers)
