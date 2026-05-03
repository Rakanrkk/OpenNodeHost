# OpenNodeHost Architecture

## 1. Design Goal

OpenNodeHost is a remote execution runtime for AI agents.

It is designed for a model where:

- one controller/agent remains the single planner
- remote machines act only as execution nodes
- command execution is structured, stateful, and retrievable
- transport can ride on SSH without exposing a public control port

## 2. System Layers

### Controller Plane
The controller plane is the user-facing orchestrator.

Responsibilities:
- select target nodes
- open and close sessions
- start execs
- inspect status
- retrieve output
- interrupt work

Examples of controllers:
- Hermes
- Codex-like agents
- Claude Code-like agents
- CLI scripts
- MCP hosts through an adapter

### Transport Plane
The transport plane carries controller <-> node traffic.

Initial transport target:
- stdio over SSH

Future optional transports:
- local Unix socket
- localhost TCP via SSH forwarding
- HTTP/gRPC for trusted private networks

### Node Plane
The node plane is made of lightweight remote node hosts.

Each node host:
- runs on one target machine
- receives structured requests
- manages local sessions and execs
- buffers outputs locally
- returns structured metadata

### Execution Plane
The execution plane is local to each node.

Examples:
- Linux: bash / subprocess / PTY
- WSL2: bash / subprocess / PTY
- Windows: PowerShell / subprocess / optional PTY

## 3. Core Objects

### Node
A remote execution endpoint.

Suggested fields:
- node_id
- platform
- hostname
- capabilities
- online
- last_seen

### Session
A persistent command context on a node.

Suggested fields:
- session_id
- node_id
- shell_type
- cwd
- env summary
- state
- created_at
- last_active_at

### Exec
A single command execution record.

Suggested fields:
- exec_id
- session_id
- command
- status
- exit_code
- stdout_size
- stderr_size
- created_at
- started_at
- finished_at
- truncated
- more_available

## 4. Execution Model

OpenNodeHost should not model execution as a one-shot text return.

Instead:
1. controller requests exec start
2. node host assigns exec_id
3. node host runs command locally
4. node host stores stdout/stderr in local buffers
5. controller polls status or receives an event
6. controller fetches output in chunks

This avoids making a single RPC response carry the entire execution result.

## 5. Output Model

Outputs should be first-class data, not incidental text.

Requirements:
- stdout and stderr tracked separately
- output retrievable by offset/limit
- preview available in initial responses
- full output available incrementally
- truncation represented explicitly in metadata

## 6. Session Model

Sessions are first-class and long-lived.

Requirements:
- session open/close lifecycle
- persistent cwd and shell context where supported
- state tracking: idle/running/closed/error/dirty
- shell-specific behavior hidden behind node host

## 7. Error Model

Errors should be layered:
- transport error
- node unavailable
- session error
- exec launch error
- process non-zero exit
- output retrieval error

A non-zero process exit must not be conflated with transport failure.

## 8. Compatibility Goal

The core runtime must remain agent-agnostic.

That means:
- no Hermes-specific protocol in core
- no MCP-only core design
- CLI/API/MCP adapters should wrap the same runtime model

## 9. Initial Scope

Phase 1:
- Linux node host
- stdio-over-SSH transport
- Node / Session / Exec data model
- output buffering and pagination
- controller-side CLI

Phase 2:
- Windows node host
- WSL2 node host
- MCP adapter
- event streaming

## 10. Out of Scope (Initial)

- full multi-tenant auth platform
- browser UI
- workflow engine
- distributed scheduler
- file sync platform
- remote desktop / media control
