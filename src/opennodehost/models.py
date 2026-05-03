from dataclasses import dataclass
from typing import Literal, Optional

NodePlatform = Literal["linux", "windows", "wsl2"]
SessionState = Literal["idle", "running", "closed", "error", "dirty"]
ExecStatus = Literal["queued", "running", "completed", "failed", "interrupted"]


@dataclass
class Node:
    node_id: str
    platform: NodePlatform
    hostname: str
    online: bool = False
    last_seen: Optional[str] = None


@dataclass
class Session:
    session_id: str
    node_id: str
    shell_type: str
    state: SessionState = "idle"
    cwd: Optional[str] = None


@dataclass
class Exec:
    exec_id: str
    session_id: str
    command: str
    status: ExecStatus = "queued"
    exit_code: Optional[int] = None
    stdout_size: int = 0
    stderr_size: int = 0
    more_available: bool = False
