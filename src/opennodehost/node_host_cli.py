from __future__ import annotations

import argparse
import json
import platform
import sys
import uuid
from pathlib import Path

from opennodehost.runtime import NodeHostRuntime


VERSION = "0.2.0"


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def error_response(req_id: str | None, err_type: str, message: str) -> dict:
    return {"id": req_id, "ok": False, "error": {"type": err_type, "message": message}}


def run_stdio() -> int:
    node_id = f"bootstrap-{uuid.uuid4()}"
    state = NodeHostRuntime(node_id=node_id, base_dir=Path.cwd())
    emit({
        "event": "node.ready",
        "payload": {
            "node_id": node_id,
            "platform": platform.system().lower(),
            "protocol": "stdio-jsonl",
            "version": VERSION,
        },
    })

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            emit(error_response(None, "bad_json", str(e)))
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params")

        if not isinstance(req_id, str) or not req_id:
            emit(error_response(req_id, "invalid_request", "request id must be a non-empty string"))
            continue
        if not isinstance(method, str) or not method:
            emit(error_response(req_id, "invalid_request", "method must be a non-empty string"))
            continue
        if params is None:
            params = {}
        if not isinstance(params, dict):
            emit(error_response(req_id, "invalid_request", "params must be an object"))
            continue

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
                            "session.close",
                            "session.list",
                            "exec.start",
                            "exec.read",
                            "exec.status",
                            "exec.list",
                            "exec.interrupt",
                        ],
                        "protocol": "stdio-jsonl",
                        "version": VERSION,
                    },
                })
            elif method == "session.open":
                shell = params.get("shell") or ("powershell" if platform.system().lower() == "windows" else "bash")
                result = state.open_session(shell=shell, cwd=params.get("cwd"))
                emit({"id": req_id, "ok": True, "result": result})
            elif method == "session.close":
                if "session_id" not in params:
                    emit(error_response(req_id, "invalid_request", "session_id is required"))
                    continue
                emit({"id": req_id, "ok": True, "result": state.close_session(params["session_id"])})
            elif method == "session.list":
                emit({"id": req_id, "ok": True, "result": state.list_sessions()})
            elif method == "exec.start":
                if "session_id" not in params or "command" not in params:
                    emit(error_response(req_id, "invalid_request", "session_id and command are required"))
                    continue
                result = state.start_exec(params["session_id"], params["command"])
                emit({"id": req_id, "ok": True, "result": result})
            elif method == "exec.status":
                if "exec_id" not in params:
                    emit(error_response(req_id, "invalid_request", "exec_id is required"))
                    continue
                emit({"id": req_id, "ok": True, "result": state.exec_status(params["exec_id"])})
            elif method == "exec.list":
                emit({"id": req_id, "ok": True, "result": state.list_execs(params.get("session_id"))})
            elif method == "exec.interrupt":
                if "exec_id" not in params:
                    emit(error_response(req_id, "invalid_request", "exec_id is required"))
                    continue
                emit({"id": req_id, "ok": True, "result": state.interrupt_exec(params["exec_id"])})
            elif method == "exec.read":
                if "exec_id" not in params:
                    emit(error_response(req_id, "invalid_request", "exec_id is required"))
                    continue
                emit({
                    "id": req_id,
                    "ok": True,
                    "result": state.exec_read(
                        params["exec_id"],
                        params.get("stream", "stdout"),
                        int(params.get("offset", 0)),
                        int(params.get("limit", 4096)),
                    ),
                })
            else:
                emit(error_response(req_id, "not_implemented", f"method {method} not implemented"))
        except KeyError as e:
            emit(error_response(req_id, str(e).strip("'"), str(e).strip("'")))
        except ValueError as e:
            emit(error_response(req_id, "invalid_request", str(e)))
        except RuntimeError as e:
            emit(error_response(req_id, "runtime_error", str(e)))
        except Exception as e:
            emit(error_response(req_id, "runtime_error", str(e)))

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="opennodehost-node")
    parser.add_argument("--stdio", action="store_true", help="run stdio JSONL node host")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()

    if args.version:
        print(json.dumps({"name": "OpenNodeHost", "version": VERSION, "role": "node-host"}))
        return 0

    if args.stdio:
        return run_stdio()

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
