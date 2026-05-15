"""Product-level session and run shapes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoreSession:
    session_id: str


@dataclass(frozen=True)
class CoreRun:
    run_id: str
    session_id: str
    goal: str


@dataclass(frozen=True)
class CoreConversation:
    conversation_id: str
    session_id: str
    run_id: str
    goal: str
