# OpenNodeHost

OpenNodeHost is a remote execution runtime for AI agents.

It is designed for a setup where one agent remains the single planner/orchestrator, while remote Linux, Windows, and WSL2 machines act as execution nodes.

## Problem

Current approaches usually fall into one of these buckets:

- raw SSH command execution
- terminal scraping via tmux/screen
- MCP wrappers around SSH
- traditional automation frameworks like Ansible

These are useful, but they each leave gaps for agent-centric remote execution:

- command quoting and shell nesting become fragile
- large output is awkward to stream or page
- session state is not always a first-class concept
- execution status is often inferred from text instead of modeled explicitly
- Windows/Linux/WSL2 support is often uneven

## Project Goal

OpenNodeHost aims to provide a small, durable execution layer with these properties:

- agent-agnostic core
- SSH-friendly transport model
- persistent node/session/exec abstractions
- structured stdout/stderr/exit-code handling
- paged output retrieval
- compatibility with Linux, Windows, and WSL2
- adapters for CLI, MCP, and API use

## Current Status

Current milestone: **local MVP working, SSH path scaffolded**.

What works now:
- local controller <-> node-host stdio JSONL protocol
- `session.open`, `session.list`, `session.close`
- `exec.start`, `exec.status`, `exec.read`, `exec.list`, `exec.interrupt`
- asynchronous exec lifecycle with background process tracking
- stdout/stderr buffer files with paged reads
- controller CLI subcommands for session/exec operations
- local selftest and pytest coverage

What is still early:
- real SSH integration is scaffolded but not yet fully validated against a remote Linux host
- no PTY mode yet
- no Windows/WSL2 validation yet
- no MCP adapter yet
- no auth/permission model yet

## Quick Start

### Requirements
- Python 3.11+
- POSIX shell for local bash-based tests
- SSH client available if using remote targets

### Install for development

```bash
cd ~/WorkSpace/OpenNodeHost
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip pytest
```

### Run tests

```bash
cd ~/WorkSpace/OpenNodeHost
. .venv/bin/activate
PYTHONPATH=src pytest -q
```

### Run the built-in selftest

```bash
cd ~/WorkSpace/OpenNodeHost
. .venv/bin/activate
PYTHONPATH=src python src/opennodehost/controller_cli.py selftest
```

Expected result:
- JSON output with `ok: true`
- session lifecycle present
- exec lifecycle present
- stdout/stderr readback present

### Optional editable install

If you want the `opennodehost` and `opennodehost-node` commands directly:

```bash
cd ~/WorkSpace/OpenNodeHost
. .venv/bin/activate
pip install -e .
```

## CLI Usage

### Open a local session

```bash
PYTHONPATH=src python src/opennodehost/controller_cli.py --json session open --shell bash
```

Or, after editable install:

```bash
opennodehost --json session open --shell bash
```

### List local sessions

```bash
PYTHONPATH=src python src/opennodehost/controller_cli.py --json session list
```

### Start an exec in a session

```bash
PYTHONPATH=src python src/opennodehost/controller_cli.py --json exec start <session_id> "printf 'hello from exec'"
```

### Check exec status

```bash
PYTHONPATH=src python src/opennodehost/controller_cli.py --json exec status <exec_id>
```

### Read stdout

```bash
PYTHONPATH=src python src/opennodehost/controller_cli.py exec read <exec_id> --stream stdout --offset 0 --limit 4096
```

### Interrupt an exec

```bash
PYTHONPATH=src python src/opennodehost/controller_cli.py --json exec interrupt <exec_id>
```

### Close a session

```bash
PYTHONPATH=src python src/opennodehost/controller_cli.py --json session close <session_id>
```

## SSH Usage

Remote execution is currently based on:

```bash
ssh -T <target> opennodehost-node --stdio
```

Controller-side SSH commands accept `--target user@host` and optional `--remote-command`.

Example:

```bash
PYTHONPATH=src python src/opennodehost/controller_cli.py --json --remote-command "python -m opennodehost.node_host_cli --stdio" session open --target user@host
```

See `docs/transport-ssh.md` for more details and caveats.

## Non-Goals

OpenNodeHost is not intended to be:

- another full autonomous coding agent
- a replacement for Ansible/Terraform/Salt
- a terminal UI product
- a remote desktop system
- a general-purpose cloud orchestration platform

## Architecture Direction

High-level architecture:

- controller plane: the user-facing orchestrator/agent
- transport plane: initially SSH-backed
- node plane: lightweight remote node host on each machine
- execution plane: local shell / PowerShell subprocess management on the node

Core objects:

- Node
- Session
- Exec

## Initial Scope

The initial version should focus on:

1. remote node host process
2. session lifecycle
3. command execution lifecycle
4. output buffering and pagination
5. Linux support first
6. Windows and WSL2 support next
7. MCP adapter after core runtime is stable

## Why this project exists

This project exists because there does not appear to be a widely adopted open-source runtime that cleanly fills the gap between:

- simple SSH wrappers
- traditional ops automation frameworks
- full remote device/node control planes such as OpenClaw nodes
