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
        target_id = req.get("id")
        while True:
            line = self.process.stdout.readline()
            if not line:
                stderr = ""
                if self.process.stderr is not None:
                    stderr = self.process.stderr.read()
                raise RuntimeError(f"node host closed stdout unexpectedly: {stderr}")
            msg = json.loads(line)
            messages.append(msg)
            if msg.get("id") == target_id:
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


def connect_ssh_stdio(target: str, remote_command: str = "opennodehost-node --stdio") -> NodeConnection:
    cmd = [
        "ssh",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
        target,
        remote_command,
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return NodeConnection(proc)


def response_result(messages: list[dict[str, Any]], request_id: str | None = None) -> dict[str, Any]:
    target_id = request_id
    if target_id is None:
        for msg in messages:
            if isinstance(msg.get("id"), str):
                target_id = msg["id"]
                break
    for msg in reversed(messages):
        if msg.get("id") != target_id:
            continue
        if msg.get("ok") is True:
            return msg["result"]
        if msg.get("ok") is False:
            error = msg.get("error", {})
            raise RuntimeError(f"{error.get('type', 'request_failed')}: {error.get('message', 'unknown error')}")
    raise RuntimeError("no response found for request")
