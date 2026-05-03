from __future__ import annotations

import subprocess
import uuid
from pathlib import Path


class NodeHostRuntime:
    def __init__(self, node_id: str, base_dir: Path) -> None:
        self.node_id = node_id
        self.sessions: dict[str, dict] = {}
        self.execs: dict[str, dict] = {}
        self.buffer_dir = base_dir / "state"
        self.buffer_dir.mkdir(parents=True, exist_ok=True)

    def open_session(self, shell: str, cwd: str | None = None) -> dict:
        session_id = f"sess-{uuid.uuid4()}"
        session = {
            "session_id": session_id,
            "node_id": self.node_id,
            "shell_type": shell,
            "state": "idle",
            "cwd": cwd or str(self.buffer_dir.parent),
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
