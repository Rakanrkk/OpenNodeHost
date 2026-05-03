from __future__ import annotations

import argparse
import json
from pathlib import Path

from opennodehost.controller_runtime import connect_local_stdio, connect_ssh_stdio, response_result


VERSION = "0.1.0"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(prog="opennodehost")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("version")
    sub.add_parser("doctor")
    sub.add_parser("selftest")

    ssh_selftest = sub.add_parser("ssh-selftest")
    ssh_selftest.add_argument("target")

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
            session_msgs = conn.request({"id": "3", "method": "session.open", "params": {"shell": "bash"}})
            session = response_result(session_msgs)
            exec_msgs = conn.request({
                "id": "4",
                "method": "exec.start",
                "params": {"session_id": session["session_id"], "command": "printf 'hello-opennodehost'"},
            })
            exec_result = response_result(exec_msgs)
            status_msgs = conn.request({"id": "5", "method": "exec.status", "params": {"exec_id": exec_result["exec_id"]}})
            read_msgs = conn.request({"id": "6", "method": "exec.read", "params": {"exec_id": exec_result["exec_id"], "stream": "stdout", "offset": 0, "limit": 4096}})
            print(json.dumps({
                "ok": True,
                "ping": ping_msgs,
                "describe": describe_msgs,
                "session": session_msgs,
                "exec": exec_msgs,
                "status": status_msgs,
                "read": read_msgs,
            }, ensure_ascii=False))
            return 0
        finally:
            conn.process.terminate()
            conn.process.wait(timeout=5)

    if args.command == "ssh-selftest":
        conn = connect_ssh_stdio(args.target)
        try:
            ping_msgs = conn.request({"id": "1", "method": "ping", "params": {}})
            print(json.dumps({"ok": True, "ping": ping_msgs}, ensure_ascii=False))
            return 0
        finally:
            conn.process.terminate()
            conn.process.wait(timeout=5)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
