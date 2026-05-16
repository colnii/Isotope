"""Lightweight state for managed Supervisor lanes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROMPT_COOLDOWN_SECONDS = 300


@dataclass(frozen=True)
class LaneState:
    name: str
    tmux_session: str | None
    last_status: str
    last_prompted_at: str | None = None
    prompt_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tmux_session": self.tmux_session,
            "last_status": self.last_status,
            "last_prompted_at": self.last_prompted_at,
            "prompt_count": self.prompt_count,
        }


def default_lane_state_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "lane_state.json"


def read_lane_states(path: Path | str) -> dict[str, LaneState]:
    state_path = Path(path).expanduser()
    if not state_path.is_file():
        return {}
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    states: dict[str, LaneState] = {}
    for name, item in raw.items():
        if not isinstance(name, str) or not isinstance(item, dict):
            continue
        state = _state_from_dict(item)
        if state is not None:
            states[name] = state
    return states


def write_lane_states(path: Path | str, states: dict[str, LaneState]) -> None:
    state_path = Path(path).expanduser()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        name: state.to_dict()
        for name, state in sorted(states.items(), key=lambda item: item[0])
    }
    state_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def prompt_cooldown_state(
    *,
    codex_home: Path | str,
    name: str,
    now: datetime | None = None,
    cooldown_seconds: int = DEFAULT_PROMPT_COOLDOWN_SECONDS,
) -> LaneState | None:
    if cooldown_seconds <= 0:
        return None
    states = read_lane_states(default_lane_state_path(codex_home))
    state = states.get(name)
    if state is None or state.last_prompted_at is None:
        return None
    prompted_at = _parse_timestamp(state.last_prompted_at)
    if prompted_at is None:
        return None
    current = _ensure_aware_utc(now or _utc_now())
    age_seconds = max(0, int((current - prompted_at).total_seconds()))
    return state if age_seconds < cooldown_seconds else None


def record_lane_prompt(
    *,
    codex_home: Path | str,
    name: str,
    tmux_session: str | None,
    status: str,
    now: datetime | None = None,
) -> LaneState:
    path = default_lane_state_path(codex_home)
    states = read_lane_states(path)
    current = _ensure_aware_utc(now or _utc_now())
    previous = states.get(name)
    prompt_count = (
        previous.prompt_count + 1
        if previous is not None and previous.last_status == status
        else 1
    )
    state = LaneState(
        name=name,
        tmux_session=tmux_session,
        last_status=status,
        last_prompted_at=current.isoformat(),
        prompt_count=prompt_count,
    )
    states[name] = state
    write_lane_states(path, states)
    return state


def _state_from_dict(raw: dict[str, Any]) -> LaneState | None:
    name = raw.get("name")
    tmux_session = raw.get("tmux_session")
    last_status = raw.get("last_status")
    last_prompted_at = raw.get("last_prompted_at")
    prompt_count = raw.get("prompt_count")
    if not isinstance(name, str) or not isinstance(last_status, str):
        return None
    if tmux_session is not None and not isinstance(tmux_session, str):
        return None
    if last_prompted_at is not None and not isinstance(last_prompted_at, str):
        return None
    if not isinstance(prompt_count, int) or prompt_count < 0:
        return None
    return LaneState(
        name=name,
        tmux_session=tmux_session,
        last_status=last_status,
        last_prompted_at=last_prompted_at,
        prompt_count=prompt_count,
    )


def _parse_timestamp(value: str) -> datetime | None:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return _ensure_aware_utc(datetime.fromisoformat(normalized))
    except ValueError:
        return None


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
