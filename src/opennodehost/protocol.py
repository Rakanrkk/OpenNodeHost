from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

MessageKind = Literal["request", "response", "event"]


@dataclass
class Request:
    id: str
    method: str
    params: dict[str, Any]


@dataclass
class Response:
    id: str | None
    ok: bool
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


@dataclass
class Event:
    event: str
    payload: dict[str, Any]
