from __future__ import annotations

import argparse
import json
from pathlib import Path

from opennodehost.controller_runtime import connect_local_stdio


VERSION = "0.1.0"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(prog="opennodehost")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("version")
    sub.add_parser("doctor")
    sub.add_parser("selftest")

    args = parser.parse_args()

    if args.command == "version":
        print(json.dumps({"name": "OpenNodeHost", "version": VERSION, "role": "controller"}))
        return 0

    if args.command == "doctor":
        print(json.dumps({"ok": True, "message": "controller bootstrap skeleton only"}))
        return 0

    if args.command == "selftest":
        conn = connect_local_stdio(_project_root())
        try:
            ping_msgs = conn.request({"id": "1", "method": "ping", "params": {}})
            describe_msgs = conn.request({"id": "2", "method": "node.describe", "params": {}})
            print(json.dumps({
                "ok": True,
                "ping": ping_msgs,
                "describe": describe_msgs,
            }, ensure_ascii=False))
            return 0
        finally:
            conn.process.terminate()
            conn.process.wait(timeout=5)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
