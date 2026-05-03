from __future__ import annotations

import subprocess
import threading
import uuid
from pathlib import Path
from typing import TextIO


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

    def close_session(self, session_id: str) -> dict:
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError("session_not_found")
        session["state"] = "closed"
        return {
            "session_id": session["session_id"],
            "node_id": session["node_id"],
            "shell_type": session["shell_type"],
            "state": session["state"],
            "cwd": session["cwd"],
        }

    def list_sessions(self) -> dict:
        sessions = [
            {
                "session_id": session["session_id"],
                "node_id": session["node_id"],
                "shell_type": session["shell_type"],
                "state": session["state"],
                "cwd": session["cwd"],
            }
            for session in self.sessions.values()
        ]
        return {"items": sessions, "count": len(sessions)}

    def start_exec(self, session_id: str, command: str) -> dict:
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError("session_not_found")
        if session["state"] == "closed":
            raise RuntimeError("session_closed")

        exec_id = f"exec-{uuid.uuid4()}"
        shell_type = session["shell_type"]

        if shell_type == "powershell":
            cmd = ["powershell", "-NoLogo", "-NoProfile", "-Command", command]
        else:
            cmd = ["bash", "-lc", command]

        stdout_path = self.buffer_dir / f"{exec_id}.stdout.log"
        stderr_path = self.buffer_dir / f"{exec_id}.stderr.log"
        stdout_path.touch()
        stderr_path.touch()

        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            cwd=session["cwd"],
        )

        record = {
            "exec_id": exec_id,
            "session_id": session_id,
            "command": command,
            "status": "running",
            "exit_code": None,
            "stdout_size": 0,
            "stderr_size": 0,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "more_available": True,
            "preview": "",
            "pid": proc.pid,
            "process": proc,
            "stdout_handle": stdout_handle,
            "stderr_handle": stderr_handle,
        }
        self.execs[exec_id] = record
        session["state"] = "running"
        watcher = threading.Thread(target=self._finalize_exec, args=(exec_id,), daemon=True)
        watcher.start()
        return self._public_exec_record(record)

    def list_execs(self, session_id: str | None = None) -> dict:
        items = []
        for record in self.execs.values():
            if session_id and record["session_id"] != session_id:
                continue
            self._refresh_exec_metadata(record)
            items.append(self._public_exec_record(record))
        return {"items": items, "count": len(items)}

    def exec_status(self, exec_id: str) -> dict:
        record = self.execs.get(exec_id)
        if not record:
            raise KeyError("exec_not_found")
        self._refresh_exec_metadata(record)
        result = self._public_exec_record(record)
        return {
            "exec_id": result["exec_id"],
            "session_id": result["session_id"],
            "status": result["status"],
            "exit_code": result["exit_code"],
            "stdout_size": result["stdout_size"],
            "stderr_size": result["stderr_size"],
            "more_available": result["more_available"],
            "pid": result["pid"],
        }

    def interrupt_exec(self, exec_id: str) -> dict:
        record = self.execs.get(exec_id)
        if not record:
            raise KeyError("exec_not_found")

        proc = record.get("process")
        if proc is None:
            self._refresh_exec_metadata(record)
            return self._public_exec_record(record)

        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        self._finalize_exec(exec_id, interrupted=True)
        return self._public_exec_record(record)

    def exec_read(self, exec_id: str, stream: str = "stdout", offset: int = 0, limit: int = 4096) -> dict:
        record = self.execs.get(exec_id)
        if not record:
            raise KeyError("exec_not_found")
        if stream not in {"stdout", "stderr"}:
            raise ValueError("invalid_stream")

        self._refresh_exec_metadata(record)
        path = Path(record[f"{stream}_path"])
        with path.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read(limit)
            next_offset = offset + len(chunk)
            eof = next_offset >= path.stat().st_size
        content = chunk.decode("utf-8", errors="replace")
        return {
            "exec_id": exec_id,
            "stream": stream,
            "offset": offset,
            "next_offset": next_offset,
            "eof": eof,
            "content": content,
        }

    def _public_exec_record(self, record: dict) -> dict:
        self._refresh_exec_metadata(record)
        return {
            "exec_id": record["exec_id"],
            "session_id": record["session_id"],
            "command": record["command"],
            "status": record["status"],
            "exit_code": record["exit_code"],
            "stdout_size": record["stdout_size"],
            "stderr_size": record["stderr_size"],
            "stdout_path": record["stdout_path"],
            "stderr_path": record["stderr_path"],
            "more_available": record["more_available"],
            "preview": record["preview"],
            "pid": record.get("pid"),
        }

    def _refresh_exec_metadata(self, record: dict) -> None:
        stdout_path = Path(record["stdout_path"])
        stderr_path = Path(record["stderr_path"])
        if stdout_path.exists():
            record["stdout_size"] = stdout_path.stat().st_size
            record["preview"] = self._read_preview(stdout_path)
        if stderr_path.exists():
            record["stderr_size"] = stderr_path.stat().st_size
        record["more_available"] = record["status"] == "running"

    def _finalize_exec(self, exec_id: str, interrupted: bool = False) -> None:
        record = self.execs.get(exec_id)
        if not record:
            return

        proc = record.get("process")
        if proc is not None:
            try:
                if proc.poll() is None and not interrupted:
                    proc.wait()
            finally:
                self._close_handle(record.get("stdout_handle"))
                self._close_handle(record.get("stderr_handle"))

            return_code = proc.returncode
        else:
            return_code = record.get("exit_code")

        if interrupted:
            record["status"] = "interrupted"
            if return_code is None:
                return_code = -15
        else:
            record["status"] = "completed" if return_code == 0 else "failed"

        record["exit_code"] = return_code
        record["process"] = None
        record["stdout_handle"] = None
        record["stderr_handle"] = None
        self._refresh_exec_metadata(record)

        session = self.sessions.get(record["session_id"])
        if session and session["state"] != "closed":
            session["state"] = "idle"

    def _read_preview(self, path: Path, limit: int = 200) -> str:
        with path.open("rb") as handle:
            data = handle.read(limit)
        return data.decode("utf-8", errors="replace")

    def _close_handle(self, handle: TextIO | None) -> None:
        if handle is not None and not handle.closed:
            handle.close()
