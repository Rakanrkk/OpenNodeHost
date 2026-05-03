import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_controller_selftest_returns_ok():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "src" / "opennodehost" / "controller_cli.py"), "selftest"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert any(msg.get("event") == "node.ready" for msg in data["ping"])
    assert any(msg.get("id") == "1" and msg.get("ok") is True for msg in data["ping"])
    assert any(msg.get("id") == "2" and msg.get("ok") is True for msg in data["describe"])
    session_result = next(msg["result"] for msg in data["session"] if msg.get("id") == "3" and msg.get("ok") is True)
    assert session_result["state"] == "idle"
    exec_result = next(msg["result"] for msg in data["exec"] if msg.get("id") == "4" and msg.get("ok") is True)
    assert exec_result["exit_code"] == 0
    status_result = next(msg["result"] for msg in data["status"] if msg.get("id") == "5" and msg.get("ok") is True)
    assert status_result["status"] == "completed"
    read_result = next(msg["result"] for msg in data["read"] if msg.get("id") == "6" and msg.get("ok") is True)
    assert "hello-opennodehost" in read_result["content"]
    assert read_result["eof"] is True
