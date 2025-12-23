# JQM - Job Queue Manager

A job queue management system for sequential command execution with HTTP and CLI interfaces.

## Overview

JQM manages a queue of jobs (shell commands) and executes them sequentially. It consists of three independent processes communicating via TCP:

- **Engine** (port 5051): Core job queue management and execution
- **HTTP Server** (port 9200): REST API and web interface
- **CLI Server** (port 9201): Command-line interface server

## Requirements

- Python 3.9.13
- No third-party packages required

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd jqm

# Run tests
python -m unittest discover tests
```

## Quick Start

### Start All Services

```bash
# Start engine, HTTP server, and CLI server in background
jqm-server start

# Check status
jqm-server status

# Stop all services
jqm-server stop
```

### Using the CLI

```bash
# Add jobs to the queue
jqm add python script.py --verbose
jqm add powershell ./test.ps1 -Config prod.xml --cwd /path/to/dir

# List all jobs
jqm list

# Start the queue
jqm queue start

# Watch progress in real-time
jqm watch
```

### Using the Web Interface

Open `http://localhost:9200` in your browser to access the web interface.

## Architecture

```
┌──────────────┐
│   Engine     │  ← Core (port 5051)
│  (process 1) │     Queue + Execution
└──────┬───────┘
       │ TCP localhost
   ────┴────────────
   │               │
┌──▼────────┐  ┌──▼────────┐
│  HTTP     │  │    CLI    │
│  Server   │  │  Server   │
│ (port     │  │ (port     │
│  9200)    │  │  9201)    │
└───────────┘  └───────────┘
```

## Job States

- **pending**: Waiting to execute
- **running**: Currently executing
- **completed**: Finished successfully (exit code 0)
- **failed**: Finished with error (exit code != 0)
- **skip**: Marked to be skipped during execution

## Queue States

- **stopped**: No automatic execution, full editing allowed
- **started**: Sequential automatic execution, limited editing
- **paused**: Waiting for resume after current job completes

## Commands

### Process Management

```bash
jqm-server start [--log-dir DIR]  # Start all services
jqm-server stop                   # Stop all services
jqm-server status                 # Check service status
jqm-server engine [OPTIONS]       # Run engine only (foreground)
jqm-server http [OPTIONS]         # Run HTTP server only (foreground)
jqm-server cli [OPTIONS]          # Run CLI server only (foreground)
```

### Job Management

```bash
jqm add <command> [args...] [--cwd DIR]  # Add job
jqm list                                  # List all jobs
jqm detail <job_id>                       # Show job details
jqm delete <job_id>                       # Delete job
jqm update <job_id> <command> [args...]   # Update job
jqm set-state <job_id> <skip|pending>     # Change job state
jqm move <job_id> <top|bottom|up|down>    # Reorder job
jqm log <job_id>                          # Show job log
```

### Queue Control

```bash
jqm queue start   # Start execution
jqm queue stop    # Stop after current job
jqm queue pause   # Pause after current job
jqm queue play    # Resume from pause
jqm queue status  # Show queue status
```

### Export/Import

```bash
jqm export <file.xml>  # Export queue to XML
jqm import <file.xml>  # Import queue from XML
```

### Real-time Monitoring

```bash
jqm watch  # Watch queue progress in real-time
```

## HTTP API

### Jobs

- `GET /api/jobs` - List all jobs
- `POST /api/jobs` - Add a job
- `GET /api/jobs/:id` - Get job details
- `PUT /api/jobs/:id` - Update job
- `DELETE /api/jobs/:id` - Delete job
- `PUT /api/jobs/:id/state` - Change job state
- `PUT /api/jobs/:id/order` - Reorder job
- `GET /api/jobs/:id/log` - Get job log

### Queue

- `GET /api/queue/state` - Get queue state
- `PUT /api/queue/state` - Change queue state
- `GET /api/queue/export` - Export queue as XML
- `POST /api/queue/import` - Import queue from XML

### Events

- `GET /api/events` - Server-Sent Events stream for real-time updates

## Development

### Project Structure

```
jqm/
├── jqm/
│   ├── common/          # Shared code (protocol, constants)
│   ├── engine/          # Engine implementation
│   ├── http_server/     # HTTP server
│   ├── cli_server/      # CLI server
│   └── cli_client/      # CLI client
├── tests/               # Unit tests
├── SPECIFICATIONS.md    # Complete project specifications
└── DEVELOPMENT_GUIDELINES.md  # Development guidelines
```

### Running Tests

```bash
# Run all tests
python -m unittest discover tests

# Run specific test module
python -m unittest tests.test_protocol

# Run with verbose output
python -m unittest discover tests -v
```

### Logging

JQM uses Python's standard logging module. Logs are written to:
- **Application logs**: stderr (configurable per component)
- **Job logs**: `./jqm_logs/job_XXX.log` (configurable via `--log-dir`)

## Configuration

### Default Ports

- Engine: 5051
- HTTP Server: 9200
- CLI Server: 9201

### Default Directories

- Job logs: `./jqm_logs`
- PID files: current directory

## Security Warning

⚠️ **JQM has NO built-in security features:**

- No authentication
- No command validation
- Executes arbitrary commands
- No sandboxing

**Only use on trusted networks. Do NOT expose to the internet.**

## Limitations

- No job cancellation (by design)
- No retry on failure
- No encryption
- Job IDs reset on engine restart
- Localhost only (by design)

## License

[Add your license here]

## Contributing

See [DEVELOPMENT_GUIDELINES.md](DEVELOPMENT_GUIDELINES.md) for coding standards and contribution guidelines.
