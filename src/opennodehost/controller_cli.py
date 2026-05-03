from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from opennodehost.controller_runtime import (
    connect_local_stdio,
    connect_ssh_stdio,
    make_persistent_local,
    make_persistent_ssh,
    response_result,
)
from opennodehost.targets import DEFAULT_TARGETS_PATH, infer_remote_command, load_targets, resolve_target, save_targets


VERSION = "0.4.0"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_connection(args: argparse.Namespace):
    if getattr(args, "target", None):
        cfg = resolve_target(args.target)
        remote_command = getattr(args, "remote_command", None) or infer_remote_command(cfg)
        return connect_ssh_stdio(args.target, remote_command=remote_command)
    return connect_local_stdio(_project_root())


def _build_persistent(args: argparse.Namespace):
    if getattr(args, "target", None):
        cfg = resolve_target(args.target)
        remote_command = getattr(args, "remote_command", None) or infer_remote_command(cfg)
        return make_persistent_ssh(args.target, remote_command=remote_command)
    return make_persistent_local(_project_root())


def _print_output(data: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, ensure_ascii=False))
        return
    if "result" in data and isinstance(data["result"], dict):
        result = data["result"]
        if set(result.keys()) == {"content", "offset", "next_offset", "eof", "stream", "exec_id"}:
            print(result["content"], end="")
            return
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _request(conn, method: str, req_id: str, params: dict) -> dict:
    messages = conn.request({"id": req_id, "method": method, "params": params})
    result = response_result(messages, req_id)
    return {"ok": True, "messages": messages, "result": result}


def main() -> int:
    parser = argparse.ArgumentParser(prog="opennodehost")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--remote-command", default=os.environ.get("OPENNODEHOST_REMOTE_COMMAND"), help="remote node-host launch command for SSH mode")
    parser.add_argument("--targets-file", default=os.environ.get("OPENNODEHOST_TARGETS_FILE"), help="override path to targets.yaml")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("version")
    sub.add_parser("doctor")
    sub.add_parser("selftest")

    ssh_selftest = sub.add_parser("ssh-selftest")
    ssh_selftest.add_argument("target")

    target_parser = sub.add_parser("target")
    target_sub = target_parser.add_subparsers(dest="target_command")

    target_sub.add_parser("list")

    target_show = target_sub.add_parser("show")
    target_show.add_argument("name")

    target_doctor = target_sub.add_parser("doctor")
    target_doctor.add_argument("name")

    target_init = target_sub.add_parser("init")
    target_init.add_argument("name")
    target_init.add_argument("--host", required=True)
    target_init.add_argument("--user")
    target_init.add_argument("--port", type=int)
    target_init.add_argument("--platform")
    target_init.add_argument("--shell")
    target_init.add_argument("--python-bin")
    target_init.add_argument("--launch-mode", default="auto", choices=["auto", "installed", "python-module", "custom"])
    target_init.add_argument("--launch-command")

    session = sub.add_parser("session")
    session_sub = session.add_subparsers(dest="session_command")

    session_open = session_sub.add_parser("open")
    session_open.add_argument("--target")
    session_open.add_argument("--shell", default="bash")
    session_open.add_argument("--cwd")

    session_list = session_sub.add_parser("list")
    session_list.add_argument("--target")

    session_close = session_sub.add_parser("close")
    session_close.add_argument("session_id")
    session_close.add_argument("--target")

    exec_parser = sub.add_parser("exec")
    exec_sub = exec_parser.add_subparsers(dest="exec_command")

    exec_start = exec_sub.add_parser("start")
    exec_start.add_argument("session_id")
    exec_start.add_argument("command_text")
    exec_start.add_argument("--target")

    exec_status = exec_sub.add_parser("status")
    exec_status.add_argument("exec_id")
    exec_status.add_argument("--target")

    exec_read = exec_sub.add_parser("read")
    exec_read.add_argument("exec_id")
    exec_read.add_argument("--target")
    exec_read.add_argument("--stream", default="stdout", choices=["stdout", "stderr"])
    exec_read.add_argument("--offset", type=int, default=0)
    exec_read.add_argument("--limit", type=int, default=4096)

    exec_list = exec_sub.add_parser("list")
    exec_list.add_argument("--target")
    exec_list.add_argument("--session-id")

    exec_interrupt = exec_sub.add_parser("interrupt")
    exec_interrupt.add_argument("exec_id")
    exec_interrupt.add_argument("--target")

    workflow = sub.add_parser("workflow")
    workflow_sub = workflow.add_subparsers(dest="workflow_command")

    run_command = workflow_sub.add_parser("run")
    run_command.add_argument("command_text")
    run_command.add_argument("--target")
    run_command.add_argument("--shell", default="bash")
    run_command.add_argument("--cwd")
    run_command.add_argument("--stream", default="stdout", choices=["stdout", "stderr"])

    args = parser.parse_args()

    if args.command == "version":
        print(json.dumps({"name": "OpenNodeHost", "version": VERSION, "role": "controller"}))
        return 0

    if args.command == "doctor":
        print(json.dumps({"ok": True, "message": "controller bootstrap skeleton only"}))
        return 0

    if args.command == "target":
        data = load_targets(args.targets_file)
        if args.target_command == "list":
            payload = {"ok": True, "targets": data.get("targets", {}), "path": str(Path(args.targets_file).expanduser()) if args.targets_file else str(DEFAULT_TARGETS_PATH)}
            _print_output(payload, args.json)
            return 0
        if args.target_command == "show":
            payload = {"ok": True, "target": resolve_target(args.name, args.targets_file)}
            _print_output(payload, args.json)
            return 0
        if args.target_command == "init":
            targets = data.setdefault("targets", {})
            entry = {
                "transport": "ssh",
                "host": args.host,
                "user": args.user,
                "shell": args.shell or ("powershell" if (args.platform or "").lower() == "windows" else "bash"),
                "platform": args.platform,
                "python_bin": args.python_bin,
                "launch": {"mode": args.launch_mode},
            }
            if args.port:
                entry["port"] = args.port
            if args.launch_command:
                entry["launch"]["command"] = args.launch_command
            targets[args.name] = {k: v for k, v in entry.items() if v not in (None, {})}
            path = save_targets(data, args.targets_file)
            payload = {"ok": True, "saved": str(path), "target": resolve_target(args.name, str(path))}
            _print_output(payload, args.json)
            return 0
        if args.target_command == "doctor":
            cfg = resolve_target(args.name, args.targets_file)
            payload = {
                "ok": True,
                "target": cfg,
                "checks": {
                    "transport": cfg.get("transport"),
                    "resolved_target": cfg.get("target"),
                    "remote_command": infer_remote_command(cfg),
                },
            }
            _print_output(payload, args.json)
            return 0
        parser.error("unknown target subcommand")

    if args.command == "selftest":
        conn = connect_local_stdio(_project_root())
        try:
            ping_msgs = conn.request({"id": "1", "method": "ping", "params": {}})
            describe_msgs = conn.request({"id": "2", "method": "node.describe", "params": {}})
            session_msgs = conn.request({"id": "3", "method": "session.open", "params": {"shell": "bash"}})
            session = response_result(session_msgs, "3")

            list_sessions_msgs = conn.request({"id": "4", "method": "session.list", "params": {}})
            exec_msgs = conn.request({
                "id": "5",
                "method": "exec.start",
                "params": {"session_id": session["session_id"], "command": "python3 - <<'PY'\nimport sys\nprint(\"hello-opennodehost\")\nprint(\"stderr-line\", file=sys.stderr)\nPY"},
            })
            exec_result = response_result(exec_msgs, "5")
            status_msgs = conn.request({"id": "6", "method": "exec.status", "params": {"exec_id": exec_result["exec_id"]}})
            status_result = response_result(status_msgs, "6")
            while status_result["status"] == "running":
                status_msgs = conn.request({"id": "6", "method": "exec.status", "params": {"exec_id": exec_result["exec_id"]}})
                status_result = response_result(status_msgs, "6")
            read_stdout_msgs = conn.request({"id": "7", "method": "exec.read", "params": {"exec_id": exec_result["exec_id"], "stream": "stdout", "offset": 0, "limit": 8}})
            read_stdout_more_msgs = conn.request({"id": "8", "method": "exec.read", "params": {"exec_id": exec_result["exec_id"], "stream": "stdout", "offset": 8, "limit": 4096}})
            read_stderr_msgs = conn.request({"id": "9", "method": "exec.read", "params": {"exec_id": exec_result["exec_id"], "stream": "stderr", "offset": 0, "limit": 4096}})
            list_execs_msgs = conn.request({"id": "10", "method": "exec.list", "params": {"session_id": session["session_id"]}})
            close_session_msgs = conn.request({"id": "11", "method": "session.close", "params": {"session_id": session["session_id"]}})
            print(json.dumps({
                "ok": True,
                "ping": ping_msgs,
                "describe": describe_msgs,
                "session": session_msgs,
                "session_list": list_sessions_msgs,
                "exec": exec_msgs,
                "status": status_msgs,
                "read_stdout": read_stdout_msgs,
                "read_stdout_more": read_stdout_more_msgs,
                "read_stderr": read_stderr_msgs,
                "exec_list": list_execs_msgs,
                "close_session": close_session_msgs,
            }, ensure_ascii=False))
            return 0
        finally:
            conn.process.terminate()
            conn.process.wait(timeout=5)

    if args.command == "ssh-selftest":
        conn = connect_ssh_stdio(args.target, args.remote_command or "opennodehost-node --stdio")
        try:
            ping_msgs = conn.request({"id": "1", "method": "ping", "params": {}})
            print(json.dumps({"ok": True, "ping": ping_msgs}, ensure_ascii=False))
            return 0
        finally:
            conn.process.terminate()
            conn.process.wait(timeout=5)

    if args.command == "workflow" and args.workflow_command == "run":
        controller = _build_persistent(args)
        try:
            session_payload = controller.call("session.open", {"shell": args.shell, "cwd": args.cwd})
            session_id = session_payload["result"]["session_id"]
            exec_payload = controller.call("exec.start", {"session_id": session_id, "command": args.command_text})
            exec_id = exec_payload["result"]["exec_id"]
            status_payload = controller.call("exec.status", {"exec_id": exec_id})
            while status_payload["result"]["status"] == "running":
                status_payload = controller.call("exec.status", {"exec_id": exec_id})
            read_payload = controller.call("exec.read", {"exec_id": exec_id, "stream": args.stream, "offset": 0, "limit": 65536})
            close_payload = controller.call("session.close", {"session_id": session_id})
            payload = {
                "ok": True,
                "session": session_payload,
                "exec": exec_payload,
                "status": status_payload,
                "read": read_payload,
                "close": close_payload,
            }
            _print_output(payload, args.json)
            return 0
        finally:
            controller.close()

    try:
        if args.command == "session":
            conn = _build_connection(args)
            try:
                if args.session_command == "open":
                    payload = _request(conn, "session.open", "session-open", {"shell": args.shell, "cwd": args.cwd})
                elif args.session_command == "list":
                    payload = _request(conn, "session.list", "session-list", {})
                elif args.session_command == "close":
                    payload = _request(conn, "session.close", "session-close", {"session_id": args.session_id})
                else:
                    parser.error("unknown session subcommand")
                _print_output(payload, args.json)
                return 0
            finally:
                conn.process.terminate()
                conn.process.wait(timeout=5)

        if args.command == "exec":
            conn = _build_connection(args)
            try:
                if args.exec_command == "start":
                    payload = _request(conn, "exec.start", "exec-start", {"session_id": args.session_id, "command": args.command_text})
                elif args.exec_command == "status":
                    payload = _request(conn, "exec.status", "exec-status", {"exec_id": args.exec_id})
                elif args.exec_command == "read":
                    payload = _request(conn, "exec.read", "exec-read", {"exec_id": args.exec_id, "stream": args.stream, "offset": args.offset, "limit": args.limit})
                elif args.exec_command == "list":
                    params = {}
                    if args.session_id:
                        params["session_id"] = args.session_id
                    payload = _request(conn, "exec.list", "exec-list", params)
                elif args.exec_command == "interrupt":
                    payload = _request(conn, "exec.interrupt", "exec-interrupt", {"exec_id": args.exec_id})
                else:
                    parser.error("unknown exec subcommand")
                _print_output(payload, args.json)
                return 0
            finally:
                conn.process.terminate()
                conn.process.wait(timeout=5)
    except RuntimeError as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        else:
            print(str(e))
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
