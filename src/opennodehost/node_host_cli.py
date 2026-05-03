from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import uuid
from pathlib import Path


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


class RuntimeState:
    def __init__(self) -> None:
        self.node_id = f"bootstrap-{uuid.uuid4()}"
        self.sessions: dict[str, dict] = {}
        self.execs: dict[str, dict] = {}
        self.buffer_dir = Path.cwd() / "state"
        self.buffer_dir.mkdir(parents=True, exist_ok=True)

    def open_session(self, shell: str | None = None) -> dict:
        session_id = f"sess-{uuid.uuid4()}"
        shell_type = shell or ("powershell" if platform.system().lower() == "windows" else "bash")
        session = {
            "session_id": session_id,
            "node_id": self.node_id,
            "shell_type": shell_type,
            "state": "idle",
            "cwd": str(Path.cwd()),
        }
        self.sessions[session_id] = session
        return session

    def start_exec(self, session_id: str, command: str) -> dict:
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError("session_not_found")

        exec_id = f"exec-{uuid.uuid4()}"
        shell_type = session["shell_type"]

        if shell_type == "powershell":
            cmd = ["powershell", "-NoLogo", "-NoProfile", "-Command", command]
        else:
            cmd = ["bash", "-lc", command]

        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=session["cwd"])
        stdout = proc.stdout
        stderr = proc.stderr

        stdout_path = self.buffer_dir / f"{exec_id}.stdout.log"
        stderr_path = self.buffer_dir / f"{exec_id}.stderr.log"
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")

        record = {
            "exec_id": exec_id,
            "session_id": session_id,
            "command": command,
            "status": "completed" if proc.returncode == 0 else "failed",
            "exit_code": proc.returncode,
            "stdout_size": len(stdout.encode("utf-8")),
            "stderr_size": len(stderr.encode("utf-8")),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "more_available": False,
            "preview": stdout[:200],
        }
        self.execs[exec_id] = record
        return record

    def exec_status(self, exec_id: str) -> dict:
        record = self.execs.get(exec_id)
        if not record:
            raise KeyError("exec_not_found")
        return {
            "exec_id": record["exec_id"],
            "session_id": record["session_id"],
            "status": record["status"],
            "exit_code": record["exit_code"],
            "stdout_size": record["stdout_size"],
            "stderr_size": record["stderr_size"],
            "more_available": record["more_available"],
        }

    def exec_read(self, exec_id: str, stream: str = "stdout", offset: int = 0, limit: int = 4096) -> dict:
        record = self.execs.get(exec_id)
        if not record:
            raise KeyError("exec_not_found")
        path = Path(record[f"{stream}_path"])
        data = path.read_text(encoding="utf-8")
        chunk = data[offset:offset + limit]
        next_offset = offset + len(chunk)
        eof = next_offset >= len(data)
        return {
            "exec_id": exec_id,
            "stream": stream,
            "offset": offset,
            "next_offset": next_offset,
            "eof": eof,
            "content": chunk,
        }


def run_stdio() -> int:
    state = RuntimeState()
    emit({
        "event": "node.ready",
        "payload": {
            "node_id": state.node_id,
            "platform": platform.system().lower(),
            "protocol": "stdio-jsonl",
            "version": "0.1.0"
        }
    })

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            emit({"ok": False, "error": {"type": "bad_json", "message": str(e)}})
            continue

        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params", {})

        try:
            if method == "ping":
                emit({"id": req_id, "ok": True, "result": {"pong": True}})
            elif method == "node.describe":
                emit({
                    "id": req_id,
                    "ok": True,
                    "result": {
                        "platform": platform.system().lower(),
                        "capabilities": [
                            "session.open",
                            "exec.start",
                            "exec.read",
                            "exec.status"
                        ],
                        "protocol": "stdio-jsonl",
                        "version": "0.1.0"
                    }
                })
            elif method == "session.open":
                result = state.open_session(params.get("shell"))
                emit({"id": req_id, "ok": True, "result": result})
            elif method == "exec.start":
                result = state.start_exec(params["session_id"], params["command"])
                emit({
                    "id": req_id,
                    "ok": True,
                    "result": {
                        "exec_id": result["exec_id"],
                        "session_id": result["session_id"],
                        "status": result["status"],
                        "exit_code": result["exit_code"],
                        "stdout_size": result["stdout_size"],
                        "stderr_size": result["stderr_size"],
                        "more_available": result["more_available"],
                        "preview": result["preview"],
                    }
                })
            elif method == "exec.status":
                emit({"id": req_id, "ok": True, "result": state.exec_status(params["exec_id"])})
            elif method == "exec.read":
                emit({
                    "id": req_id,
                    "ok": True,
                    "result": state.exec_read(
                        params["exec_id"],
                        params.get("stream", "stdout"),
                        int(params.get("offset", 0)),
                        int(params.get("limit", 4096)),
                    )
                })
            else:
                emit({"id": req_id, "ok": False, "error": {"type": "not_implemented", "message": f"method {method} not implemented"}})
        except KeyError as e:
            emit({"id": req_id, "ok": False, "error": {"type": str(e), "message": str(e)}})
        except Exception as e:
            emit({"id": req_id, "ok": False, "error": {"type": "runtime_error", "message": str(e)}})

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="opennodehost-node")
    parser.add_argument("--stdio", action="store_true", help="run stdio JSONL node host")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()

    if args.version:
        print(json.dumps({"name": "OpenNodeHost", "version": "0.1.0", "role": "node-host"}))
        return 0

    if args.stdio:
        return run_stdio()

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
