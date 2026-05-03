from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_TARGETS_PATH = Path.home() / ".config" / "opennodehost" / "targets.yaml"


def load_targets(path: str | None = None) -> dict[str, Any]:
    target_path = Path(path).expanduser() if path else DEFAULT_TARGETS_PATH
    if not target_path.exists():
        return {"targets": {}}
    data = yaml.safe_load(target_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError("targets file must contain a mapping")
    data.setdefault("targets", {})
    if not isinstance(data["targets"], dict):
        raise RuntimeError("targets must be a mapping")
    return data


def save_targets(data: dict[str, Any], path: str | None = None) -> Path:
    target_path = Path(path).expanduser() if path else DEFAULT_TARGETS_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return target_path


def resolve_target(target: str, path: str | None = None) -> dict[str, Any]:
    data = load_targets(path)
    targets = data.get("targets", {})
    if target in targets:
        cfg = dict(targets[target])
        cfg.setdefault("name", target)
        cfg.setdefault("transport", "ssh")
        cfg.setdefault("shell", "bash")
        cfg.setdefault("launch", {"mode": "auto"})
        cfg.setdefault("target", _compose_target(cfg))
        return cfg
    return {
        "name": target,
        "transport": "ssh",
        "target": target,
        "shell": "bash",
        "launch": {"mode": "auto"},
    }


def infer_remote_command(cfg: dict[str, Any]) -> str:
    launch = cfg.get("launch", {}) or {}
    mode = launch.get("mode", "auto")
    if mode == "custom":
        command = launch.get("command")
        if not command:
            raise RuntimeError("custom launch mode requires launch.command")
        return command
    if mode == "installed":
        return "opennodehost-node --stdio"
    if mode == "python-module":
        python_bin = launch.get("python") or cfg.get("python_bin") or "python3"
        return f"{python_bin} -m opennodehost.node_host_cli --stdio"
    python_bin = launch.get("python") or cfg.get("python_bin")
    if python_bin:
        return f"{python_bin} -m opennodehost.node_host_cli --stdio"
    platform = (cfg.get("platform") or "").lower()
    if platform == "windows":
        return "python -m opennodehost.node_host_cli --stdio"
    return "opennodehost-node --stdio"


def _compose_target(cfg: dict[str, Any]) -> str:
    if "target" in cfg:
        return cfg["target"]
    user = cfg.get("user")
    host = cfg.get("host")
    if not host:
        raise RuntimeError("target config must define host or target")
    port = cfg.get("port")
    base = f"{user}@{host}" if user else str(host)
    if port:
        return base
    return base
