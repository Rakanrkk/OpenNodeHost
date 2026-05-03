from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class NodeConnection:
    process: subprocess.Popen[str]

    def request(self, req: dict[str, Any]) -> list[dict[str, Any]]:
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.write(json.dumps(req) + "\n")
        self.process.stdin.flush()

        messages: list[dict[str, Any]] = []
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("node host closed stdout unexpectedly")
            msg = json.loads(line)
            messages.append(msg)
            if msg.get("id") == req.get("id"):
                return messages


def connect_local_stdio(project_root: Path) -> NodeConnection:
    cmd = [sys.executable, str(project_root / "src" / "opennodehost" / "node_host_cli.py"), "--stdio"]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return NodeConnection(proc)


def response_result(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for msg in reversed(messages):
        if "id" in msg and msg.get("ok") is True:
            return msg["result"]
    raise RuntimeError("no successful response found")
