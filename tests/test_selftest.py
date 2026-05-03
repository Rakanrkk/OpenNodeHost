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
