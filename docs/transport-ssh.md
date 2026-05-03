# SSH Transport Strategy

## Initial strategy

OpenNodeHost uses stdio over SSH as the first transport.

Controller side pattern:

```bash
ssh -T <target> opennodehost-node --stdio
```

This means:
- SSH provides auth + encryption + connectivity
- `opennodehost-node` provides the structured execution protocol
- stdin/stdout carry JSONL request/response/event messages

## Current controller defaults

The controller currently adds these SSH options:

- `-T`
- `-o BatchMode=yes`
- `-o StrictHostKeyChecking=yes`
- `-o ConnectTimeout=10`
- `-o ServerAliveInterval=30`
- `-o ServerAliveCountMax=3`

These defaults are intended to make non-interactive automation less fragile.

## PTY note

OpenNodeHost does **not** turn the SSH transport itself into an interactive TTY. SSH remains a stdio JSONL control channel.

Interactive shell behavior is implemented *inside the remote node-host*:
- Unix targets use real PTY-backed shells
- Windows targets currently use a pipe-fallback interactive shell mode

This preserves protocol stability while still enabling interactive-style execution.

## Why this approach

Compared with raw SSH command execution, this avoids pushing the entire control protocol through nested shell quoting.

Compared with public WebSocket node services, this avoids exposing a new public control port.

## Remote prerequisites

For a remote Linux node to work, you currently need:

- SSH access to the target
- a Python environment on the target
- a runnable node-host entrypoint on the target
- a remote shell environment that does not emit banners/noise on stdout before protocol messages

In practice, the safest current remote command is often explicit, for example:

```bash
python -m opennodehost.node_host_cli --stdio
```

You can pass that from the controller with `--remote-command`.

## Controller examples

### SSH selftest

```bash
PYTHONPATH=src python src/opennodehost/controller_cli.py \
  --remote-command "python -m opennodehost.node_host_cli --stdio" \
  ssh-selftest user@host
```

### Open a remote session

```bash
PYTHONPATH=src python src/opennodehost/controller_cli.py --json \
  --remote-command "python -m opennodehost.node_host_cli --stdio" \
  session open --target user@host --shell bash
```

### Run a full remote workflow on one persistent connection

```bash
PYTHONPATH=src python src/opennodehost/controller_cli.py --json \
  --remote-command "python -m opennodehost.node_host_cli --stdio" \
  workflow run "uname -a" --target user@host --shell bash
```

### Start a remote exec

```bash
PYTHONPATH=src python src/opennodehost/controller_cli.py --json \
  --remote-command "python -m opennodehost.node_host_cli --stdio" \
  exec start <session_id> "uname -a" --target user@host
```

## Common failure modes

### 1. Remote command not found
Symptoms:
- SSH connects but the protocol never starts
- controller reports transport/protocol failure

Check:
- is `opennodehost-node` installed on the remote PATH?
- if not, use `--remote-command "python -m opennodehost.node_host_cli --stdio"`

### 2. Shell startup noise pollutes stdout
Symptoms:
- JSON decode failures
- protocol starts with unexpected text

Check:
- remote shell startup files
- MOTD / login banners
- custom shell prompts or print statements in non-interactive startup paths

### 3. Python environment mismatch
Symptoms:
- module import errors remotely
- remote command exits immediately

Check:
- whether the remote environment has the package/module available
- whether `python` vs `python3` matters on the target

## Future options

Possible future transports:
- SSH local port forwarding to a localhost-only node service
- Unix socket on trusted local systems
- HTTP/gRPC in private networks
