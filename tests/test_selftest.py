import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

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
