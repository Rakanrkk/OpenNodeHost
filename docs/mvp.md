# OpenNodeHost MVP

## MVP Goal

Validate that a controller can reliably manage structured remote execution on a Linux node over SSH without relying on raw one-shot SSH command output.

## Success Criteria

The MVP is successful if it can:

1. connect to a Linux node over SSH
2. start a remote node-host process over stdio
3. open a persistent session
4. execute commands with exec IDs
5. retrieve output incrementally
6. report exit status cleanly
7. survive large outputs better than raw SSH command wrappers

## MVP Components

### Local controller CLI
Commands:
- opennodehost nodes list
- opennodehost connect <target>
- opennodehost session open <target>
- opennodehost exec start <session_id> -- <command>
- opennodehost exec status <exec_id>
- opennodehost exec read <exec_id> [--offset N] [--limit N]
- opennodehost session close <session_id>

### Remote Linux node host
Responsibilities:
- read JSON requests from stdin
- execute commands locally
- manage session state
- persist output buffers
- emit JSON responses/events to stdout

## Minimum Data Contracts

### session.open result
- session_id
- node_id
- shell_type
- state
- cwd

### exec.start result
- exec_id
- session_id
- status
- exit_code
- stdout_size
- stderr_size
- preview
- more_available

### exec.status result
- exec_id
- status
- exit_code
- stdout_size
- stderr_size
- more_available

### exec.read result
- exec_id
- stream
- offset
- next_offset
- eof
- content

## Current MVP State

Currently implemented locally:
- `ping`
- `node.describe`
- `session.open`
- `exec.start`
- `exec.status`
- `exec.read`
- controller selftest covering the full local stdio path

## Explicit Non-Goals For MVP

- Windows support
- WSL2 support
- PTY mode
- MCP adapter
- web UI
- advanced auth
- file transfer
- resumable disconnected sessions beyond active SSH transport
