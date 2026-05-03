from __future__ import annotations

import argparse
import json
import platform
import sys
import uuid
from pathlib import Path

from opennodehost.runtime import NodeHostRuntime


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def run_stdio() -> int:
    node_id = f"bootstrap-{uuid.uuid4()}"
    state = NodeHostRuntime(node_id=node_id, base_dir=Path.cwd())
    emit({
        "event": "node.ready",
        "payload": {
            "node_id": node_id,
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
                shell = params.get("shell") or ("powershell" if platform.system().lower() == "windows" else "bash")
                result = state.open_session(shell=shell, cwd=params.get("cwd"))
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
