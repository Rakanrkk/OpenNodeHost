import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from opennodehost.controller_runtime import NodeConnection, connect_ssh_stdio, response_result
from opennodehost.runtime import NodeHostRuntime


ROOT = Path(__file__).resolve().parents[1]
TEST_ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def test_controller_selftest_returns_ok():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "src" / "opennodehost" / "controller_cli.py"), "selftest"],
        capture_output=True,
        text=True,
        check=True,
        env=TEST_ENV,
    )
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert any(msg.get("event") == "node.ready" for msg in data["ping"])
    assert any(msg.get("id") == "1" and msg.get("ok") is True for msg in data["ping"])
    assert any(msg.get("id") == "2" and msg.get("ok") is True for msg in data["describe"])
    session_result = next(msg["result"] for msg in data["session"] if msg.get("id") == "3" and msg.get("ok") is True)
    assert session_result["state"] == "idle"
    list_sessions_result = next(msg["result"] for msg in data["session_list"] if msg.get("id") == "4" and msg.get("ok") is True)
    assert list_sessions_result["count"] == 1
    exec_result = next(msg["result"] for msg in data["exec"] if msg.get("id") == "5" and msg.get("ok") is True)
    assert exec_result["status"] in {"running", "completed"}
    status_result = next(msg["result"] for msg in data["status"] if msg.get("id") == "6" and msg.get("ok") is True)
    assert status_result["status"] == "completed"
    read_stdout_result = next(msg["result"] for msg in data["read_stdout"] if msg.get("id") == "7" and msg.get("ok") is True)
    read_stdout_more_result = next(msg["result"] for msg in data["read_stdout_more"] if msg.get("id") == "8" and msg.get("ok") is True)
    assert read_stdout_result["content"] + read_stdout_more_result["content"] == "hello-opennodehost\n"
    read_stderr_result = next(msg["result"] for msg in data["read_stderr"] if msg.get("id") == "9" and msg.get("ok") is True)
    assert "stderr-line" in read_stderr_result["content"]
    exec_list_result = next(msg["result"] for msg in data["exec_list"] if msg.get("id") == "10" and msg.get("ok") is True)
    assert exec_list_result["count"] == 1
    close_session_result = next(msg["result"] for msg in data["close_session"] if msg.get("id") == "11" and msg.get("ok") is True)
    assert close_session_result["state"] == "closed"


def test_controller_cli_real_commands_local():
    open_proc = subprocess.run(
        [sys.executable, str(ROOT / "src" / "opennodehost" / "controller_cli.py"), "--json", "session", "open", "--shell", "bash"],
        capture_output=True,
        text=True,
        check=True,
        env=TEST_ENV,
    )
    opened = json.loads(open_proc.stdout)
    assert opened["ok"] is True
    assert opened["result"]["session_id"].startswith("sess-")


def test_node_host_version_entrypoint():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "src" / "opennodehost" / "node_host_cli.py"), "--version"],
        capture_output=True,
        text=True,
        check=True,
        env=TEST_ENV,
    )
    data = json.loads(proc.stdout)
    assert data["role"] == "node-host"


def test_runtime_session_and_exec_flow(tmp_path: Path):
    runtime = NodeHostRuntime(node_id="node-1", base_dir=tmp_path)
    session = runtime.open_session(shell="bash", cwd=str(tmp_path))
    assert session["state"] == "idle"

    listed = runtime.list_sessions()
    assert listed["count"] == 1

    exec_record = runtime.start_exec(session["session_id"], "python3 - <<'PY'\nimport sys\nprint('A'*5000)\nprint('ERR', file=sys.stderr)\nPY")
    assert exec_record["status"] == "running"

    status = None
    for _ in range(100):
        status = runtime.exec_status(exec_record["exec_id"])
        if status["status"] != "running":
            break
        time.sleep(0.02)
    assert status is not None
    assert status["status"] == "completed"
    assert status["stderr_size"] > 0
    first = runtime.exec_read(exec_record["exec_id"], offset=0, limit=1024)
    second = runtime.exec_read(exec_record["exec_id"], offset=first["next_offset"], limit=10000)
    assert first["eof"] is False
    assert second["eof"] is True
    assert len(first["content"] + second["content"]) >= 5001
    stderr = runtime.exec_read(exec_record["exec_id"], stream="stderr", offset=0, limit=100)
    assert "ERR" in stderr["content"]

    execs = runtime.list_execs(session["session_id"])
    assert execs["count"] == 1

    closed = runtime.close_session(session["session_id"])
    assert closed["state"] == "closed"


def test_runtime_interrupt_exec(tmp_path: Path):
    runtime = NodeHostRuntime(node_id="node-1", base_dir=tmp_path)
    session = runtime.open_session(shell="bash", cwd=str(tmp_path))
    exec_record = runtime.start_exec(session["session_id"], "sleep 10")
    interrupted = runtime.interrupt_exec(exec_record["exec_id"])
    assert interrupted["status"] == "interrupted"
    status = runtime.exec_status(exec_record["exec_id"])
    assert status["status"] == "interrupted"


def test_runtime_failed_exec_and_closed_session(tmp_path: Path):
    runtime = NodeHostRuntime(node_id="node-1", base_dir=tmp_path)
    session = runtime.open_session(shell="bash", cwd=str(tmp_path))
    exec_record = runtime.start_exec(session["session_id"], "python3 - <<'PY'\nraise SystemExit(7)\nPY")
    for _ in range(100):
        status = runtime.exec_status(exec_record["exec_id"])
        if status["status"] != "running":
            break
        time.sleep(0.01)
    assert status["status"] == "failed"
    assert status["exit_code"] == 7
    runtime.close_session(session["session_id"])
    with pytest.raises(RuntimeError):
        runtime.start_exec(session["session_id"], "echo should-fail")


def test_runtime_missing_records_and_invalid_stream(tmp_path: Path):
    runtime = NodeHostRuntime(node_id="node-1", base_dir=tmp_path)
    with pytest.raises(KeyError):
        runtime.exec_status("missing")
    with pytest.raises(KeyError):
        runtime.close_session("missing")
    session = runtime.open_session(shell="bash", cwd=str(tmp_path))
    exec_record = runtime.start_exec(session["session_id"], "printf 'ok'")
    for _ in range(100):
        status = runtime.exec_status(exec_record["exec_id"])
        if status["status"] != "running":
            break
        time.sleep(0.01)
    with pytest.raises(ValueError):
        runtime.exec_read(exec_record["exec_id"], stream="invalid")


def test_node_connection_request_collects_event_and_response():
    process = type("FakeProcess", (), {})()
    process.stdin = io.StringIO()
    process.stdout = io.StringIO('{"event":"node.ready","payload":{}}\n{"id":"1","ok":true,"result":{"pong":true}}\n')
    process.stderr = io.StringIO("")
    conn = NodeConnection(process=process)
    messages = conn.request({"id": "1", "method": "ping", "params": {}})
    assert messages[0]["event"] == "node.ready"
    assert messages[-1]["result"]["pong"] is True


def test_node_connection_request_raises_on_closed_stdout():
    process = type("FakeProcess", (), {})()
    process.stdin = io.StringIO()
    process.stdout = io.StringIO("")
    process.stderr = io.StringIO("remote crashed")
    conn = NodeConnection(process=process)
    with pytest.raises(RuntimeError, match="remote crashed"):
        conn.request({"id": "1", "method": "ping", "params": {}})


def test_response_result_errors_and_missing_response():
    with pytest.raises(RuntimeError, match="bad_request: no session"):
        response_result([{"id": "x", "ok": False, "error": {"type": "bad_request", "message": "no session"}}], "x")
    with pytest.raises(RuntimeError, match="no response found"):
        response_result([{"event": "node.ready", "payload": {}}], "x")


def test_connect_ssh_stdio_builds_expected_ssh_command():
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        process = type("FakeProcess", (), {})()
        process.stdin = io.StringIO()
        process.stdout = io.StringIO("")
        process.stderr = io.StringIO("")
        return process

    with patch("opennodehost.controller_runtime.subprocess.Popen", side_effect=fake_popen):
        connect_ssh_stdio("user@example.com", remote_command="python -m opennodehost.node_host_cli --stdio")

    cmd = captured["cmd"]
    assert cmd[:2] == ["ssh", "-T"]
    assert "BatchMode=yes" in cmd
    assert "StrictHostKeyChecking=yes" in cmd
    assert "ConnectTimeout=10" in cmd
    assert "ServerAliveInterval=30" in cmd
    assert "ServerAliveCountMax=3" in cmd
    assert cmd[-2] == "user@example.com"
    assert cmd[-1] == "python -m opennodehost.node_host_cli --stdio"
