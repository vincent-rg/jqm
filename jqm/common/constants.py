"""Constants and default configuration values for JQM."""

# Network configuration
DEFAULT_ENGINE_HOST = "localhost"
DEFAULT_ENGINE_PORT = 5051
DEFAULT_HTTP_PORT = 9200
DEFAULT_CLI_PORT = 9201

# Reconnection settings
RECONNECT_INTERVAL_SECONDS = 3
RECONNECT_MAX_ATTEMPTS = 10  # 10 attempts * 3 seconds = 30 seconds max

# Shutdown settings
SHUTDOWN_TIMEOUT_SECONDS = 10

# Logging configuration
DEFAULT_LOG_DIR = "./jqm_logs"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Job states
STATE_PENDING = "pending"
STATE_RUNNING = "running"
STATE_COMPLETED = "completed"
STATE_FAILED = "failed"
STATE_SKIP = "skip"

# Queue states
QUEUE_STATE_STOPPED = "stopped"
QUEUE_STATE_STARTED = "started"
QUEUE_STATE_PAUSED = "paused"

# Protocol
MESSAGE_LENGTH_PREFIX_SIZE = 8  # 8 bytes for length prefix
MESSAGE_ENCODING = "utf-8"

# PID files
PID_FILE_ENGINE = "jqm_engine.pid"
PID_FILE_HTTP = "jqm_http.pid"
PID_FILE_CLI = "jqm_cli.pid"

# Reorder actions
REORDER_TOP = "top"
REORDER_BOTTOM = "bottom"
REORDER_UP = "up"
REORDER_DOWN = "down"

# Import modes
IMPORT_MODE_REPLACE = "replace"
IMPORT_MODE_APPEND = "append"
