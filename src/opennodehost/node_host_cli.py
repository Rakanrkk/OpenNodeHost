from __future__ import annotations

import argparse
import json
import platform
import sys
import uuid


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def run_stdio() -> int:
    emit({
        "event": "node.ready",
        "payload": {
            "node_id": f"bootstrap-{uuid.uuid4()}",
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

        if method == "ping":
            emit({"id": req_id, "ok": True, "result": {"pong": True}})
        elif method == "node.describe":
            emit({
                "id": req_id,
                "ok": True,
                "result": {
                    "platform": platform.system().lower(),
                    "capabilities": ["session.open", "exec.start", "exec.read", "exec.status"],
                    "protocol": "stdio-jsonl",
                    "version": "0.1.0"
                }
            })
        else:
            emit({"id": req_id, "ok": False, "error": {"type": "not_implemented", "message": f"method {method} not implemented"}})

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
