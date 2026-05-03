from __future__ import annotations

import os
import select
import signal
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any, TextIO

try:
    from winpty import PtyProcess as WinPtyProcess
except ImportError:
    WinPtyProcess = None

if os.name != "nt":
    import pty
else:
    pty = None


class NodeHostRuntime:
    def __init__(
        self,
        node_id: str,
        base_dir: Path,
        *,
        force_platform: str | None = None,
        pty_backend: Any | None = None,
    ) -> None:
        self.node_id = node_id
        self.sessions: dict[str, dict] = {}
        self.execs: dict[str, dict] = {}
        self.ptys: dict[str, dict] = {}
        self.buffer_dir = base_dir / "state"
        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        self.platform = force_platform or ("windows" if os.name == "nt" else "unix")
        if pty_backend is None:
            self.pty_backend = WinPtyProcess
        elif pty_backend is False:
            self.pty_backend = None
        else:
            self.pty_backend = pty_backend

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
        for pty_id, record in list(self.ptys.items()):
            if record["session_id"] == session_id and record["status"] == "running":
                self.close_pty(pty_id)
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

    def open_pty(self, session_id: str, shell: str | None = None, cwd: str | None = None, cols: int = 80, rows: int = 24) -> dict:
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError("session_not_found")
        if session["state"] == "closed":
            raise RuntimeError("session_closed")

        if self.platform == "windows":
            if self.pty_backend is not None:
                return self._open_windows_conpty(session_id, shell, cwd, cols, rows)
            return self._open_pipe_fallback(session_id, shell, cwd, cols, rows)
        return self._open_unix_pty(session_id, shell, cwd, cols, rows)

    def write_pty(self, pty_id: str, data: str) -> dict:
        record = self.ptys.get(pty_id)
        if not record:
            raise KeyError("pty_not_found")
        if record["status"] != "running":
            raise RuntimeError("pty_closed")
        encoded = data.encode("utf-8")
        mode = record["mode"]
        if mode == "pty":
            written = os.write(record["master_fd"], encoded)
        elif mode == "conpty":
            pty_proc = record.get("pty_process")
            if pty_proc is None:
                raise RuntimeError("pty_closed")
            written = pty_proc.write(encoded)
        else:
            stdin = record.get("stdin")
            if stdin is None:
                raise RuntimeError("pty_closed")
            stdin.write(data)
            stdin.flush()
            written = len(encoded)
        return {"pty_id": pty_id, "bytes_written": written}

    def read_pty(self, pty_id: str, offset: int = 0, limit: int = 4096) -> dict:
        record = self.ptys.get(pty_id)
        if not record:
            raise KeyError("pty_not_found")
        self._refresh_pty_metadata(record)
        path = Path(record["output_path"])
        with path.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read(limit)
            next_offset = offset + len(chunk)
            eof = next_offset >= path.stat().st_size and record["status"] != "running"
        content = chunk.decode("utf-8", errors="replace")
        return {
            "pty_id": pty_id,
            "offset": offset,
            "next_offset": next_offset,
            "eof": eof,
            "content": content,
        }

    def status_pty(self, pty_id: str) -> dict:
        record = self.ptys.get(pty_id)
        if not record:
            raise KeyError("pty_not_found")
        self._refresh_pty_metadata(record)
        result = self._public_pty_record(record)
        return {
            "pty_id": result["pty_id"],
            "session_id": result["session_id"],
            "status": result["status"],
            "pid": result["pid"],
            "output_size": result["output_size"],
            "mode": result["mode"],
            "exit_code": result["exit_code"],
        }

    def list_ptys(self, session_id: str | None = None) -> dict:
        items = []
        for record in self.ptys.values():
            if session_id and record["session_id"] != session_id:
                continue
            self._refresh_pty_metadata(record)
            items.append(self._public_pty_record(record))
        return {"items": items, "count": len(items)}

    def close_pty(self, pty_id: str) -> dict:
        record = self.ptys.get(pty_id)
        if not record:
            raise KeyError("pty_not_found")
        proc = record.get("process")
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        pty_proc = record.get("pty_process")
        if pty_proc is not None and self._pty_process_is_alive(pty_proc):
            try:
                pty_proc.close(True)
            except TypeError:
                pty_proc.close()
        self._finalize_pty(pty_id)
        return self._public_pty_record(record)

    def _open_unix_pty(self, session_id: str, shell: str | None, cwd: str | None, cols: int, rows: int) -> dict:
        session = self.sessions[session_id]
        pty_id = f"pty-{uuid.uuid4()}"
        shell_cmd = shell or session["shell_type"] or "bash"
        if shell_cmd == "powershell":
            shell_cmd = "/bin/bash"
        if shell_cmd == "bash":
            cmd = ["/bin/bash", "-i"]
        else:
            cmd = [shell_cmd, "-i"]

        master_fd, slave_fd = pty.openpty()
        output_path = self.buffer_dir / f"{pty_id}.tty.log"
        output_path.touch()
        output_handle = output_path.open("ab")
        proc = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd or session["cwd"],
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave_fd)

        record = {
            "pty_id": pty_id,
            "session_id": session_id,
            "shell_type": shell_cmd,
            "status": "running",
            "pid": proc.pid,
            "process": proc,
            "pty_process": None,
            "master_fd": master_fd,
            "stdin": None,
            "output_path": str(output_path),
            "output_handle": output_handle,
            "output_size": 0,
            "cwd": cwd or session["cwd"],
            "cols": cols,
            "rows": rows,
            "mode": "pty",
            "preview": "",
            "exit_code": None,
        }
        self.ptys[pty_id] = record
        session["state"] = "running"
        reader = threading.Thread(target=self._pty_reader, args=(pty_id,), daemon=True)
        reader.start()
        return self._public_pty_record(record)

    def _open_windows_conpty(self, session_id: str, shell: str | None, cwd: str | None, cols: int, rows: int) -> dict:
        session = self.sessions[session_id]
        pty_id = f"pty-{uuid.uuid4()}"
        shell_cmd = shell or session["shell_type"] or "powershell"
        argv = self._windows_shell_argv(shell_cmd)
        output_path = self.buffer_dir / f"{pty_id}.tty.log"
        output_path.touch()
        output_handle = output_path.open("ab")
        pty_proc = self.pty_backend.spawn(argv, cwd=cwd or session["cwd"], dimensions=(rows, cols))
        record = {
            "pty_id": pty_id,
            "session_id": session_id,
            "shell_type": shell_cmd,
            "status": "running",
            "pid": getattr(pty_proc, "pid", None),
            "process": None,
            "pty_process": pty_proc,
            "master_fd": None,
            "stdin": None,
            "output_path": str(output_path),
            "output_handle": output_handle,
            "output_size": 0,
            "cwd": cwd or session["cwd"],
            "cols": cols,
            "rows": rows,
            "mode": "conpty",
            "preview": "",
            "exit_code": None,
        }
        self.ptys[pty_id] = record
        session["state"] = "running"
        reader = threading.Thread(target=self._conpty_reader, args=(pty_id,), daemon=True)
        reader.start()
        return self._public_pty_record(record)

    def _open_pipe_fallback(self, session_id: str, shell: str | None, cwd: str | None, cols: int, rows: int) -> dict:
        session = self.sessions[session_id]
        pty_id = f"pty-{uuid.uuid4()}"
        shell_cmd = shell or session["shell_type"] or "powershell"
        if shell_cmd == "powershell":
            cmd = ["powershell", "-NoLogo", "-NoProfile"]
        else:
            cmd = ["cmd.exe"]
        output_path = self.buffer_dir / f"{pty_id}.tty.log"
        output_path.touch()
        output_handle = output_path.open("ab")
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=cwd or session["cwd"],
        )
        record = {
            "pty_id": pty_id,
            "session_id": session_id,
            "shell_type": shell_cmd,
            "status": "running",
            "pid": proc.pid,
            "process": proc,
            "pty_process": None,
            "master_fd": None,
            "stdin": proc.stdin,
            "stdout": proc.stdout,
            "output_path": str(output_path),
            "output_handle": output_handle,
            "output_size": 0,
            "cwd": cwd or session["cwd"],
            "cols": cols,
            "rows": rows,
            "mode": "pipe-fallback",
            "preview": "",
            "exit_code": None,
        }
        self.ptys[pty_id] = record
        session["state"] = "running"
        reader = threading.Thread(target=self._pipe_reader, args=(pty_id,), daemon=True)
        reader.start()
        return self._public_pty_record(record)

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

    def _public_pty_record(self, record: dict) -> dict:
        self._refresh_pty_metadata(record)
        return {
            "pty_id": record["pty_id"],
            "session_id": record["session_id"],
            "shell_type": record["shell_type"],
            "status": record["status"],
            "pid": record["pid"],
            "output_path": record["output_path"],
            "output_size": record["output_size"],
            "cwd": record["cwd"],
            "cols": record["cols"],
            "rows": record["rows"],
            "mode": record["mode"],
            "preview": record["preview"],
            "exit_code": record["exit_code"],
        }

    def _refresh_pty_metadata(self, record: dict) -> None:
        path = Path(record["output_path"])
        if path.exists():
            record["output_size"] = path.stat().st_size
            record["preview"] = self._read_preview(path)
        if record.get("mode") == "conpty":
            pty_proc = record.get("pty_process")
            if pty_proc is not None and not self._pty_process_is_alive(pty_proc) and record["status"] == "running":
                self._finalize_pty(record["pty_id"])
            return
        proc = record.get("process")
        if proc and proc.poll() is not None and record["status"] == "running":
            self._finalize_pty(record["pty_id"])

    def _pty_reader(self, pty_id: str) -> None:
        record = self.ptys.get(pty_id)
        if not record:
            return
        master_fd = record["master_fd"]
        output_handle = record["output_handle"]
        try:
            while True:
                ready, _, _ = select.select([master_fd], [], [], 0.1)
                if master_fd in ready:
                    try:
                        chunk = os.read(master_fd, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output_handle.write(chunk)
                    output_handle.flush()
                proc = record.get("process")
                if proc and proc.poll() is not None and not ready:
                    break
        finally:
            self._finalize_pty(pty_id)

    def _pipe_reader(self, pty_id: str) -> None:
        record = self.ptys.get(pty_id)
        if not record:
            return
        stdout = record.get("stdout")
        output_handle = record["output_handle"]
        try:
            while True:
                if stdout is None:
                    break
                line = stdout.readline()
                if not line:
                    break
                output_handle.write(line.encode("utf-8", errors="replace"))
                output_handle.flush()
        finally:
            self._finalize_pty(pty_id)

    def _conpty_reader(self, pty_id: str) -> None:
        record = self.ptys.get(pty_id)
        if not record:
            return
        pty_proc = record.get("pty_process")
        output_handle = record["output_handle"]
        if pty_proc is None:
            self._finalize_pty(pty_id)
            return
        try:
            while True:
                try:
                    chunk = pty_proc.read(4096)
                except EOFError:
                    break
                except OSError:
                    break
                if not chunk:
                    if not self._pty_process_is_alive(pty_proc):
                        break
                    continue
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8", errors="replace")
                output_handle.write(chunk)
                output_handle.flush()
        finally:
            self._finalize_pty(pty_id)

    def _finalize_pty(self, pty_id: str) -> None:
        record = self.ptys.get(pty_id)
        if not record:
            return
        if record["status"] == "closed":
            return
        mode = record.get("mode")
        if mode == "conpty":
            pty_proc = record.get("pty_process")
            if pty_proc is not None and self._pty_process_is_alive(pty_proc):
                return
            exit_code = getattr(pty_proc, "exitstatus", None) if pty_proc is not None else record.get("exit_code")
        else:
            proc = record.get("process")
            if proc is not None and proc.poll() is None:
                return
            exit_code = proc.returncode if proc else record.get("exit_code")
        record["exit_code"] = exit_code
        record["status"] = "closed"
        self._close_handle(record.get("output_handle"))
        record["output_handle"] = None
        if record.get("mode") == "pty" and record.get("master_fd") is not None:
            try:
                os.close(record["master_fd"])
            except OSError:
                pass
        self._close_handle(record.get("stdin"))
        session = self.sessions.get(record["session_id"])
        if session and session["state"] != "closed":
            session["state"] = "idle"
        self._refresh_pty_metadata(record)

    def _read_preview(self, path: Path, limit: int = 200) -> str:
        with path.open("rb") as handle:
            data = handle.read(limit)
        return data.decode("utf-8", errors="replace")

    def _close_handle(self, handle: TextIO | None) -> None:
        if handle is not None and not handle.closed:
            handle.close()

    def _pty_process_is_alive(self, pty_proc: Any) -> bool:
        if hasattr(pty_proc, "isalive"):
            return bool(pty_proc.isalive())
        return getattr(pty_proc, "exitstatus", None) is None

    def _windows_shell_argv(self, shell_cmd: str) -> list[str]:
        normalized = (shell_cmd or "powershell").lower()
        if normalized in {"powershell", "pwsh", "powershell.exe"}:
            return ["powershell.exe", "-NoLogo", "-NoProfile"]
        if normalized in {"cmd", "cmd.exe"}:
            return ["cmd.exe"]
        return [shell_cmd]
