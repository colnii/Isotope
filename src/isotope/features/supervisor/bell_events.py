"""tmux bell event helpers for Codex Supervisor."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class BellEvent:
    name: str
    tmux_session: str
    created_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "event": "bell",
            "name": self.name,
            "tmux_session": self.tmux_session,
            "created_at": self.created_at,
        }


def default_bell_events_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "bell_events.jsonl"


def install_tmux_bell_hook(
    *,
    codex_home: Path | str,
    name: str,
    tmux_session: str,
    run: Callable[..., Any],
) -> None:
    event_path = default_bell_events_path(codex_home)
    event_path.parent.mkdir(parents=True, exist_ok=True)
    shell_script = _bell_hook_shell_script(
        event_path=event_path,
        name=name,
        tmux_session=tmux_session,
    )
    hook = "run-shell -b " + shlex.quote(shell_script)
    run(
        ["tmux", "set-hook", "-t", tmux_session, "alert-bell", hook],
        check=True,
        text=True,
        capture_output=True,
    )


def read_latest_bell_events(path: Path | str) -> dict[str, BellEvent]:
    event_path = Path(path).expanduser()
    if not event_path.is_file():
        return {}
    latest: dict[str, BellEvent] = {}
    try:
        lines = event_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        event = _event_from_dict(raw)
        if event is None:
            continue
        previous = latest.get(event.tmux_session)
        if previous is None or event.created_at >= previous.created_at:
            latest[event.tmux_session] = event
    return latest


def _bell_hook_shell_script(
    *,
    event_path: Path,
    name: str,
    tmux_session: str,
) -> str:
    path_text = str(event_path)
    return (
        "mkdir -p "
        + shlex.quote(str(event_path.parent))
        + " && "
        + "printf "
        + shlex.quote(
            '{"event":"bell","name":"%s","tmux_session":"%s","created_at":"%s"}\\n'
        )
        + " "
        + shlex.quote(name)
        + " "
        + shlex.quote(tmux_session)
        + ' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"'
        + " >> "
        + shlex.quote(path_text)
    )


def _event_from_dict(raw: dict[str, Any]) -> BellEvent | None:
    if raw.get("event") != "bell":
        return None
    name = raw.get("name")
    tmux_session = raw.get("tmux_session")
    created_at = raw.get("created_at")
    if not isinstance(name, str) or not name:
        return None
    if not isinstance(tmux_session, str) or not tmux_session:
        return None
    if not isinstance(created_at, str) or not created_at:
        return None
    return BellEvent(name=name, tmux_session=tmux_session, created_at=created_at)
