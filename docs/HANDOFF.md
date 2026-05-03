# OpenNodeHost Handoff Notes

This document is intended to let a future agent or session take over the project quickly and safely.

## 1. Project Identity

- Project name: OpenNodeHost
- Repository path: `/Users/rakan/WorkSpace/OpenNodeHost`
- GitHub repository: `https://github.com/Rakanrkk/OpenNodeHost`
- Primary goal: build an agent-agnostic remote execution runtime for AI agents.

The intended use model is:
- one main agent/controller remains the planner
- remote Linux / Windows / WSL2 machines act as execution nodes
- transport should favor SSH-carried control rather than exposing a public node control port by default
- MCP should be an adapter later, not the core identity

## 2. Why this project exists

The project is meant to fill the gap between:
- raw SSH command execution
- ssh-mcp style wrappers
- traditional automation frameworks like Ansible
- heavier node/control-plane systems such as OpenClaw nodes

The key abstraction target is not “another SSH tool”, but:
- Node
- Session
- Exec
- Output buffering / pagination
- Structured status + result retrieval

## 3. Key design decisions already made

### 3.1 Core architecture
The project currently assumes four layers:
- controller plane
- transport plane
- node plane
- execution plane

Current preferred transport:
- stdio over SSH

Meaning:
- SSH handles connectivity, auth, and encryption
- a remote `opennodehost-node --stdio` process handles structured protocol messages
- controller speaks JSONL request/response/events over stdin/stdout

### 3.2 Compatibility target
The core should be usable by multiple agents/tools, not just Hermes.
This includes potential future use by:
- Hermes
- Codex-like agents
- Claude Code-like tools
- MCP hosts (via adapter)
- plain CLI scripts

### 3.3 Packaging direction
Current direction is Python-only core first.
Reasons:
- faster iteration
- cross-platform enough for the current scope
- lower complexity while validating protocol/runtime ideas

Planned packaging shape:
- controller entrypoint: `opennodehost`
- remote node host entrypoint: `opennodehost-node`

Recommended distribution direction (not fully implemented yet):
- controller: pipx / uv tool
- node-host: Python install first, Windows standalone packaging later if needed

## 4. Current implementation status

### 4.1 Implemented files of interest

Top-level:
- `README.md`
- `CHANGELOG.md`
- `pyproject.toml`

Docs:
- `docs/architecture.md`
- `docs/mvp.md`
- `docs/protocol.md`
- `docs/transport-ssh.md`

Source:
- `src/opennodehost/controller_cli.py`
- `src/opennodehost/controller_runtime.py`
- `src/opennodehost/node_host_cli.py`
- `src/opennodehost/runtime.py`
- `src/opennodehost/models.py`
- `src/opennodehost/protocol.py`

Tests:
- `tests/test_selftest.py`

CI:
- `.github/workflows/ci.yml`

Examples:
- `examples/targets.example.yaml`

### 4.2 What actually works now
Currently the project has a local selftest path that works end-to-end on the local machine.

The selftest does this:
1. controller starts local node-host over stdio
2. receives `node.ready` event
3. sends `ping`
4. sends `node.describe`
5. sends `session.open`
6. sends `exec.start`
7. sends `exec.status`
8. sends `exec.read`

The current command used in selftest is effectively:
- `printf 'hello-opennodehost'`

So there is already a minimal structured execution loop, not just a handshake.

### 4.3 Current implemented protocol surface
Implemented:
- `ping`
- `node.describe`
- `session.open`
- `exec.start`
- `exec.status`
- `exec.read`

Not implemented yet but expected next:
- `session.close`
- `session.list`
- `exec.list`
- `exec.interrupt`

### 4.4 Current runtime behavior
Current runtime is intentionally minimal:
- node-host creates in-memory session and exec registries
- exec is currently synchronous via local subprocess execution
- shell defaults to `bash` on non-Windows, `powershell` on Windows
- stdout/stderr are buffered into files under a `state/` directory in the project cwd
- `exec.read` reads from those files with offset/limit

Limitations of current runtime:
- sessions do not yet preserve a real interactive shell process across multiple commands
- no PTY support yet
- no asynchronous/background exec lifecycle yet
- no true SSH remote target integration tested yet
- no Windows real-world validation yet
- no WSL2-specific handling yet

## 5. How to run what exists

### 5.1 Local virtual environment used during development
A local venv exists in the project directory:
- `/Users/rakan/WorkSpace/OpenNodeHost/.venv`

Development commands used successfully:

```bash
cd /Users/rakan/WorkSpace/OpenNodeHost
. .venv/bin/activate
PYTHONPATH=src python -m py_compile src/opennodehost/*.py
PYTHONPATH=src python src/opennodehost/controller_cli.py selftest
PYTHONPATH=src python -m pytest -q
```

Expected local result currently:
- selftest returns JSON showing ping/describe/session/exec/status/read
- pytest passes

### 5.2 Node host direct version check
```bash
cd /Users/rakan/WorkSpace/OpenNodeHost
. .venv/bin/activate
PYTHONPATH=src python src/opennodehost/node_host_cli.py --version
```

## 6. Git history checkpoints already created

The following commits were created and pushed during this session:
- `feat: bootstrap protocol and stdio node host`
- `feat: add local stdio selftest and CI`
- `feat: implement minimal session and exec flow`
- `refactor: extract runtime and add ssh stdio skeleton`

Use git log to confirm exact hashes if needed.

## 7. Important constraints from the user

These matter a lot and future sessions should respect them.

### 7.1 Language / communication
- Always use Chinese with the user unless explicitly asked otherwise.
- Do not mix in random foreign-language words.
- The user explicitly corrected this.

### 7.2 Working style
- The user wants sustained autonomous progress.
- Do not stop for routine status updates.
- Only interrupt the user if there is a truly necessary design decision or an external prerequisite the user must provide.

### 7.3 Scope of autonomy
The user has already enabled YOLO / reduced approval mode for this project workflow.
Within project scope, it is acceptable to:
- edit files
- create directories
- run tests
- commit git changes
- push to GitHub

Do not stop to ask again for routine project operations inside the agreed workspace.

### 7.4 Project placement
- All project work should live under `~/WorkSpace/`
- This project specifically lives at `~/WorkSpace/OpenNodeHost`

### 7.5 Product preference
The user prefers:
- Hermes remains the single main brain/controller
- remote machines are execution nodes / hands and feet
- not remote autonomous agents thinking independently
- not fragile single-line SSH command wrappers
- not relying heavily on obscure low-adoption MCP remote shell projects

### 7.6 Security posture for this project
The user explicitly said the target systems are not important and command-level restriction is not a top concern here.
This means:
- do not over-rotate into heavy approval/allowlist/security UX too early
- architecture clarity and execution stability are more important for MVP

## 8. Why not just use existing ssh-mcp or tmux scraping
This was discussed heavily with the user.
The settled distinction is:
- many ssh-mcp style tools are SSH bridges / tool wrappers
- OpenNodeHost is intended as a remote execution runtime / node host abstraction

Specific differences emphasized:
- session is a first-class object
- exec is a first-class object
- output retrieval is structured and paged
- transport should not rely on scraping terminal UI state
- core should not be MCP-only

This distinction is important because the user is sensitive to pointless reinvention. Any future work should preserve this differentiation.

## 9. OpenClaw influence that is intentionally borrowed
The project is allowed to learn from OpenClaw’s node architecture at a high level.
Useful concepts already identified:
- Gateway / Node split
- long-lived node connections
- request/response IDs
- node identity / token concepts
- capability declaration
- event-oriented node signaling

But the project should not blindly copy:
- public network-facing WebSocket node exposure as the default
- heavyweight messaging/canvas/media product surface
- a broad security/pairing UX before core execution runtime exists

For this project, SSH-carried transport is currently preferred over a public WebSocket node service.

## 10. Hermes configuration issue that came up during this session
This is not part of OpenNodeHost itself, but it happened during the work and may matter if future sessions see weird Hermes behavior.

Problem observed:
- another TUI was routing `provider: custom` to `https://openrouter.ai/api/v1`
- request failed with HTTP 401 Missing Authentication header

Fix applied to:
- `~/.hermes/config.yaml`

Key repair:
- changed top-level `model.provider` from `custom` to `custom:ciii-codex`
- set `model.base_url` to `https://codex.ciii.club/v1`
- set `model.context_length: 1000000`
- normalized auxiliary compression provider to `custom:ciii-codex`

If future sessions see provider-routing confusion, inspect `~/.hermes/config.yaml` first.

## 11. Suggested next development steps
These are the most natural next tasks.

### Near-term priority
1. real controller subcommands instead of mostly `selftest`
   - `session-open`
   - `exec-start`
   - `exec-status`
   - `exec-read`

2. implement basic management primitives
   - `session.list`
   - `session.close`
   - `exec.list`
   - `exec.interrupt`

3. evolve runtime beyond purely synchronous subprocess execution
   - define whether exec lifecycle remains sync first or moves to background async jobs

4. validate SSH stdio path against an actual remote Linux host
   - current `connect_ssh_stdio()` is only a skeleton, not yet validated in practice

### Medium-term
5. add explicit error type normalization
6. add Windows validation path
7. add WSL2 handling strategy
8. decide when to introduce MCP adapter

## 12. Practical warnings for future sessions

1. Do not stop progress just to report progress; the user explicitly dislikes that.
2. Always test code before claiming progress.
3. Every meaningful milestone should be committed and pushed.
4. Keep the architecture reusable and cross-agent, not Hermes-specific.
5. Avoid drifting into “another ssh-mcp” in naming or product shape.

## 13. Short project summary for a future agent

OpenNodeHost is currently a Python-based early-stage remote execution runtime project.
It already has:
- docs
- packaging skeleton
- CI
- local stdio controller/node-host handshake
- minimal session and exec lifecycle
- buffered output reading
- test coverage for the current selftest path

It does NOT yet have:
- real user-facing controller commands
- remote SSH runtime validation
- persistent live shell sessions
- async exec management
- Windows/WSL2 real support
- MCP adapter

A future agent should continue from the runtime/control-plane direction, keep communication in Chinese, avoid unnecessary interruptions, and commit/push regularly.
