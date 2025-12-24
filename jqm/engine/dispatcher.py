"""Command dispatcher for Engine API.

Handles incoming commands and dispatches them to the appropriate
JobQueue operations.
"""

import logging
from typing import Any, Optional

from jqm.common.protocol import create_response
from jqm.engine.queue import InvalidOperationError, JobNotFoundError, JobQueue

logger = logging.getLogger(__name__)


class CommandDispatcher:
    """Dispatches API commands to JobQueue operations.

    Handles command validation, execution, and response formatting.
    """

    def __init__(self, queue: JobQueue, log_dir: str):
        """Initialize the command dispatcher.

        Args:
            queue: JobQueue instance to operate on
            log_dir: Directory where job logs are stored
        """
        self.queue = queue
        self.log_dir = log_dir

    def dispatch(self, message: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a command message to the appropriate handler.

        Args:
            message: Command message from client

        Returns:
            Response message to send back to client
        """
        cmd = message.get("cmd")
        if not cmd:
            return create_response(success=False, error="Missing 'cmd' field")

        # Map commands to handler methods
        handlers = {
            "list_jobs": self._handle_list_jobs,
            "add_job": self._handle_add_job,
            "delete_job": self._handle_delete_job,
            "update_job": self._handle_update_job,
            "set_job_state": self._handle_set_job_state,
            "reorder_job": self._handle_reorder_job,
            "get_queue_state": self._handle_get_queue_state,
            "set_queue_state": self._handle_set_queue_state,
            "get_job_log": self._handle_get_job_log,
            "export_queue": self._handle_export_queue,
            "import_queue": self._handle_import_queue,
        }

        handler = handlers.get(cmd)
        if not handler:
            return create_response(success=False, error=f"Unknown command: {cmd}")

        try:
            return handler(message)
        except JobNotFoundError as e:
            logger.warning(f"Job not found: {e}")
            return create_response(success=False, error=str(e))
        except InvalidOperationError as e:
            logger.warning(f"Invalid operation: {e}")
            return create_response(success=False, error=str(e))
        except ValueError as e:
            logger.warning(f"Validation error: {e}")
            return create_response(success=False, error=str(e))
        except Exception as e:
            logger.error(f"Unexpected error handling command {cmd}: {e}", exc_info=True)
            return create_response(success=False, error=f"Internal error: {e}")

    def _handle_list_jobs(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle list_jobs command.

        Returns:
            Response with list of all jobs
        """
        jobs = self.queue.get_all_jobs()
        jobs_data = [job.to_dict() for job in jobs]

        return create_response(success=True, data={"jobs": jobs_data})

    def _handle_add_job(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle add_job command.

        Args:
            message: Must contain 'data' with 'command', 'args', 'cwd'

        Returns:
            Response with new job_id
        """
        data = message.get("data")
        if not data:
            return create_response(success=False, error="Missing 'data' field")

        command = data.get("command")
        args = data.get("args", [])
        cwd = data.get("cwd")

        if not command:
            return create_response(success=False, error="Missing 'command' in data")
        if not cwd:
            return create_response(success=False, error="Missing 'cwd' in data")
        if not isinstance(args, list):
            return create_response(success=False, error="'args' must be a list")

        job_id = self.queue.add_job(command, args, cwd)

        return create_response(success=True, data={"job_id": job_id})

    def _handle_delete_job(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle delete_job command.

        Args:
            message: Must contain 'job_id'

        Returns:
            Success response
        """
        job_id = message.get("job_id")
        if job_id is None:
            return create_response(success=False, error="Missing 'job_id' field")

        self.queue.delete_job(job_id)

        return create_response(success=True, data={})

    def _handle_update_job(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle update_job command.

        Args:
            message: Must contain 'job_id' and 'data' with 'command', 'args', 'cwd'

        Returns:
            Success response
        """
        job_id = message.get("job_id")
        if job_id is None:
            return create_response(success=False, error="Missing 'job_id' field")

        data = message.get("data")
        if not data:
            return create_response(success=False, error="Missing 'data' field")

        command = data.get("command")
        args = data.get("args", [])
        cwd = data.get("cwd")

        if not command:
            return create_response(success=False, error="Missing 'command' in data")
        if not cwd:
            return create_response(success=False, error="Missing 'cwd' in data")
        if not isinstance(args, list):
            return create_response(success=False, error="'args' must be a list")

        self.queue.update_job(job_id, command, args, cwd)

        return create_response(success=True, data={})

    def _handle_set_job_state(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle set_job_state command.

        Args:
            message: Must contain 'job_id' and 'state'

        Returns:
            Success response
        """
        job_id = message.get("job_id")
        if job_id is None:
            return create_response(success=False, error="Missing 'job_id' field")

        state = message.get("state")
        if not state:
            return create_response(success=False, error="Missing 'state' field")

        self.queue.set_job_state(job_id, state)

        return create_response(success=True, data={})

    def _handle_reorder_job(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle reorder_job command.

        Args:
            message: Must contain 'job_id' and 'action'

        Returns:
            Success response
        """
        job_id = message.get("job_id")
        if job_id is None:
            return create_response(success=False, error="Missing 'job_id' field")

        action = message.get("action")
        if not action:
            return create_response(success=False, error="Missing 'action' field")

        self.queue.reorder_job(job_id, action)

        return create_response(success=True, data={})

    def _handle_get_queue_state(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle get_queue_state command.

        Returns:
            Response with queue state information
        """
        info = self.queue.get_queue_info()

        return create_response(success=True, data=info)

    def _handle_set_queue_state(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle set_queue_state command.

        Args:
            message: Must contain 'state'

        Returns:
            Success response
        """
        state = message.get("state")
        if not state:
            return create_response(success=False, error="Missing 'state' field")

        self.queue.set_state(state)

        return create_response(success=True, data={})

    def _handle_get_job_log(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle get_job_log command.

        Args:
            message: Must contain 'job_id'

        Returns:
            Response with log content
        """
        job_id = message.get("job_id")
        if job_id is None:
            return create_response(success=False, error="Missing 'job_id' field")

        # Get job to verify it exists and get log file name
        job = self.queue.get_job(job_id)

        # Read log file
        log_path = f"{self.log_dir}/{job.log_file}"
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                log_content = f.read()
        except FileNotFoundError:
            log_content = ""  # Log file doesn't exist yet (job not started)
        except Exception as e:
            logger.error(f"Error reading log file {log_path}: {e}")
            return create_response(success=False, error=f"Failed to read log file: {e}")

        return create_response(success=True, data={"log": log_content})

    def _handle_export_queue(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle export_queue command.

        Returns:
            Response with XML representation of queue
        """
        # TODO: Implement XML export
        # For now, return placeholder
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n<queue>\n</queue>'

        return create_response(success=True, data={"xml": xml})

    def _handle_import_queue(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle import_queue command.

        Args:
            message: Must contain 'xml' and 'mode' (replace or append)

        Returns:
            Success response
        """
        xml = message.get("xml")
        if not xml:
            return create_response(success=False, error="Missing 'xml' field")

        mode = message.get("mode")
        if mode not in ("replace", "append"):
            return create_response(
                success=False, error="'mode' must be 'replace' or 'append'"
            )

        # TODO: Implement XML import
        # For now, return success with placeholder

        return create_response(success=True, data={})
