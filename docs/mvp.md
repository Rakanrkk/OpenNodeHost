# OpenNodeHost MVP

## MVP Goal

Validate that a controller can reliably manage structured remote execution on a Linux node over SSH without relying on raw one-shot SSH command output.

## Success Criteria

The MVP is successful if it can:

1. connect to a Linux node over SSH
2. start a remote node-host process over stdio
3. open a session
4. execute commands with exec IDs
5. retrieve output incrementally
6. report exit status cleanly
7. interrupt running work when needed
8. survive large outputs better than raw SSH command wrappers

## MVP Components

### Local controller CLI
Current implemented command families:
- `opennodehost session open [--target ...]`
- `opennodehost session list [--target ...]`
- `opennodehost session close <session_id> [--target ...]`
- `opennodehost exec start <session_id> <command> [--target ...]`
- `opennodehost exec status <exec_id> [--target ...]`
- `opennodehost exec read <exec_id> [--stream ...] [--offset N] [--limit N] [--target ...]`
- `opennodehost exec list [--session-id ...] [--target ...]`
- `opennodehost exec interrupt <exec_id> [--target ...]`
- `opennodehost selftest`
- `opennodehost ssh-selftest <target>`

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
- pid

### exec.status result
- exec_id
- status
- exit_code
- stdout_size
- stderr_size
- more_available
- pid

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
- `session.list`
- `session.close`
- `exec.start`
- `exec.status`
- `exec.read`
- `exec.list`
- `exec.interrupt`
- asynchronous exec lifecycle via background process tracking
- controller selftest covering the full local stdio path
- pytest coverage for runtime, transport mock, and protocol helper behavior

Still pending for a fully validated SSH MVP:
- real remote Linux host end-to-end validation
- remote install/bootstrap story simplification
- stronger auth/permissions model

## Explicit Non-Goals For MVP

- Windows support
- WSL2 support
- PTY mode
- MCP adapter
- web UI
- advanced auth
- file transfer
- resumable disconnected sessions beyond active SSH transport
