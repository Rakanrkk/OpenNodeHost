from __future__ import annotations

import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser(prog="opennodehost")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("version")
    sub.add_parser("doctor")

    args = parser.parse_args()

    if args.command == "version":
        print(json.dumps({"name": "OpenNodeHost", "version": "0.1.0"}))
        return 0

    if args.command == "doctor":
        print(json.dumps({"ok": True, "message": "bootstrap skeleton only"}))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
