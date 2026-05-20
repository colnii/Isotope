"""Lightweight state for managed Supervisor lanes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROMPT_COOLDOWN_SECONDS = 300
DEFAULT_MAX_CONTINUE_COUNT = 0


@dataclass(frozen=True)
class LaneState:
    name: str
    tmux_session: str | None
    last_status: str
    last_prompted_at: str | None = None
    prompt_count: int = 0
    last_prompt_kind: str | None = None
    continue_count: int = 0
    last_failure_reason: str | None = None
    last_failure_exit_code: int | None = None
    last_failure_stderr_summary: str | None = None
    last_failure_record_id: str | None = None
    last_failed_at: str | None = None
    failure_count: int = 0
    decision_timeout_request_id: str | None = None
    decision_timeout_alerted_at: str | None = None
    decision_timeout_seconds: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tmux_session": self.tmux_session,
            "last_status": self.last_status,
            "last_prompted_at": self.last_prompted_at,
            "prompt_count": self.prompt_count,
            "last_prompt_kind": self.last_prompt_kind,
            "continue_count": self.continue_count,
            "last_failure_reason": self.last_failure_reason,
            "last_failure_exit_code": self.last_failure_exit_code,
            "last_failure_stderr_summary": self.last_failure_stderr_summary,
            "last_failure_record_id": self.last_failure_record_id,
            "last_failed_at": self.last_failed_at,
            "failure_count": self.failure_count,
            "decision_timeout_request_id": self.decision_timeout_request_id,
            "decision_timeout_alerted_at": self.decision_timeout_alerted_at,
            "decision_timeout_seconds": self.decision_timeout_seconds,
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


def continue_budget_state(
    *,
    codex_home: Path | str,
    name: str,
    max_continue_count: int = DEFAULT_MAX_CONTINUE_COUNT,
) -> LaneState | None:
    if max_continue_count <= 0:
        return None
    state = read_lane_states(default_lane_state_path(codex_home)).get(name)
    if state is None:
        return None
    return state if state.continue_count >= max_continue_count else None


def lane_failure_state(
    *,
    codex_home: Path | str,
    name: str,
) -> LaneState | None:
    state = read_lane_states(default_lane_state_path(codex_home)).get(name)
    if state is None or state.last_status != "failed":
        return None
    return state if state.last_failure_reason else None


def record_lane_prompt(
    *,
    codex_home: Path | str,
    name: str,
    tmux_session: str | None,
    status: str,
    prompt_kind: str | None = None,
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
    if previous is not None and previous.last_status == status:
        continue_count = (
            previous.continue_count + 1
            if prompt_kind == "send_continue"
            else previous.continue_count
        )
    else:
        continue_count = 1 if prompt_kind == "send_continue" else 0
    state = LaneState(
        name=name,
        tmux_session=tmux_session,
        last_status=status,
        last_prompted_at=current.isoformat(),
        prompt_count=prompt_count,
        last_prompt_kind=prompt_kind,
        continue_count=continue_count,
        last_failure_reason=previous.last_failure_reason if previous is not None else None,
        last_failure_exit_code=previous.last_failure_exit_code if previous is not None else None,
        last_failure_stderr_summary=(
            previous.last_failure_stderr_summary if previous is not None else None
        ),
        last_failure_record_id=(
            previous.last_failure_record_id if previous is not None else None
        ),
        last_failed_at=previous.last_failed_at if previous is not None else None,
        failure_count=previous.failure_count if previous is not None else 0,
        decision_timeout_request_id=(
            previous.decision_timeout_request_id if previous is not None else None
        ),
        decision_timeout_alerted_at=(
            previous.decision_timeout_alerted_at if previous is not None else None
        ),
        decision_timeout_seconds=(
            previous.decision_timeout_seconds if previous is not None else None
        ),
    )
    states[name] = state
    write_lane_states(path, states)
    return state


def record_lane_failure(
    *,
    codex_home: Path | str,
    name: str,
    tmux_session: str | None,
    reason: str,
    exit_code: int | None = None,
    stderr_summary: str | None = None,
    record_id: str | None = None,
    now: datetime | None = None,
) -> LaneState:
    path = default_lane_state_path(codex_home)
    states = read_lane_states(path)
    current = _ensure_aware_utc(now or _utc_now())
    previous = states.get(name)
    same_failure = (
        previous is not None
        and previous.last_status == "failed"
        and previous.last_failure_reason == reason
        and previous.last_failure_exit_code == exit_code
        and previous.last_failure_stderr_summary == stderr_summary
        and previous.last_failure_record_id == record_id
    )
    failure_count = (
        previous.failure_count
        if same_failure
        else previous.failure_count + 1
        if previous is not None
        else 1
    )
    state = LaneState(
        name=name,
        tmux_session=tmux_session,
        last_status="failed",
        last_prompted_at=previous.last_prompted_at if previous is not None else None,
        prompt_count=previous.prompt_count if previous is not None else 0,
        last_prompt_kind=previous.last_prompt_kind if previous is not None else None,
        continue_count=previous.continue_count if previous is not None else 0,
        last_failure_reason=reason,
        last_failure_exit_code=exit_code,
        last_failure_stderr_summary=stderr_summary,
        last_failure_record_id=record_id,
        last_failed_at=previous.last_failed_at if same_failure and previous else current.isoformat(),
        failure_count=failure_count,
        decision_timeout_request_id=(
            previous.decision_timeout_request_id if previous is not None else None
        ),
        decision_timeout_alerted_at=(
            previous.decision_timeout_alerted_at if previous is not None else None
        ),
        decision_timeout_seconds=(
            previous.decision_timeout_seconds if previous is not None else None
        ),
    )
    states[name] = state
    write_lane_states(path, states)
    return state


def record_lane_decision_timeout(
    *,
    codex_home: Path | str,
    name: str,
    request_id: str,
    timeout_seconds: int,
    now: datetime | None = None,
) -> tuple[LaneState, bool]:
    path = default_lane_state_path(codex_home)
    states = read_lane_states(path)
    current = _ensure_aware_utc(now or _utc_now())
    previous = states.get(name)
    already_alerted = (
        previous is not None
        and previous.decision_timeout_request_id == request_id
        and previous.decision_timeout_alerted_at is not None
    )
    state = LaneState(
        name=name,
        tmux_session=previous.tmux_session if previous is not None else None,
        last_status=previous.last_status if previous is not None else "needs_user",
        last_prompted_at=previous.last_prompted_at if previous is not None else None,
        prompt_count=previous.prompt_count if previous is not None else 0,
        last_prompt_kind=previous.last_prompt_kind if previous is not None else None,
        continue_count=previous.continue_count if previous is not None else 0,
        last_failure_reason=previous.last_failure_reason if previous is not None else None,
        last_failure_exit_code=previous.last_failure_exit_code if previous is not None else None,
        last_failure_stderr_summary=(
            previous.last_failure_stderr_summary if previous is not None else None
        ),
        last_failure_record_id=(
            previous.last_failure_record_id if previous is not None else None
        ),
        last_failed_at=previous.last_failed_at if previous is not None else None,
        failure_count=previous.failure_count if previous is not None else 0,
        decision_timeout_request_id=request_id,
        decision_timeout_alerted_at=(
            previous.decision_timeout_alerted_at
            if already_alerted and previous is not None
            else current.isoformat()
        ),
        decision_timeout_seconds=timeout_seconds,
    )
    states[name] = state
    write_lane_states(path, states)
    return state, not already_alerted


def clear_lane_decision_timeout(
    *,
    codex_home: Path | str,
    name: str,
    request_id: str | None = None,
) -> LaneState | None:
    path = default_lane_state_path(codex_home)
    states = read_lane_states(path)
    previous = states.get(name)
    if previous is None:
        return None
    if request_id is not None and previous.decision_timeout_request_id != request_id:
        return previous
    state = LaneState(
        name=previous.name,
        tmux_session=previous.tmux_session,
        last_status=previous.last_status,
        last_prompted_at=previous.last_prompted_at,
        prompt_count=previous.prompt_count,
        last_prompt_kind=previous.last_prompt_kind,
        continue_count=previous.continue_count,
        last_failure_reason=previous.last_failure_reason,
        last_failure_exit_code=previous.last_failure_exit_code,
        last_failure_stderr_summary=previous.last_failure_stderr_summary,
        last_failure_record_id=previous.last_failure_record_id,
        last_failed_at=previous.last_failed_at,
        failure_count=previous.failure_count,
        decision_timeout_request_id=None,
        decision_timeout_alerted_at=None,
        decision_timeout_seconds=None,
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
    last_prompt_kind = raw.get("last_prompt_kind")
    continue_count = raw.get("continue_count", 0)
    last_failure_reason = raw.get("last_failure_reason")
    last_failure_exit_code = raw.get("last_failure_exit_code")
    last_failure_stderr_summary = raw.get("last_failure_stderr_summary")
    last_failure_record_id = raw.get("last_failure_record_id")
    last_failed_at = raw.get("last_failed_at")
    failure_count = raw.get("failure_count", 0)
    decision_timeout_request_id = raw.get("decision_timeout_request_id")
    decision_timeout_alerted_at = raw.get("decision_timeout_alerted_at")
    decision_timeout_seconds = raw.get("decision_timeout_seconds")
    if not isinstance(name, str) or not isinstance(last_status, str):
        return None
    if tmux_session is not None and not isinstance(tmux_session, str):
        return None
    if last_prompted_at is not None and not isinstance(last_prompted_at, str):
        return None
    if not isinstance(prompt_count, int) or prompt_count < 0:
        return None
    if last_prompt_kind is not None and not isinstance(last_prompt_kind, str):
        return None
    if not isinstance(continue_count, int) or continue_count < 0:
        return None
    if last_failure_reason is not None and not isinstance(last_failure_reason, str):
        return None
    if last_failure_exit_code is not None or "last_failure_exit_code" in raw:
        if last_failure_exit_code is not None and (
            not isinstance(last_failure_exit_code, int) or last_failure_exit_code < 0
        ):
            return None
    if last_failure_stderr_summary is not None and not isinstance(
        last_failure_stderr_summary, str
    ):
        return None
    if last_failure_record_id is not None and not isinstance(last_failure_record_id, str):
        return None
    if last_failed_at is not None and not isinstance(last_failed_at, str):
        return None
    if not isinstance(failure_count, int) or failure_count < 0:
        return None
    if decision_timeout_request_id is not None and not isinstance(
        decision_timeout_request_id, str
    ):
        return None
    if decision_timeout_alerted_at is not None and not isinstance(
        decision_timeout_alerted_at, str
    ):
        return None
    if decision_timeout_seconds is not None and (
        not isinstance(decision_timeout_seconds, int)
        or decision_timeout_seconds < 0
    ):
        return None
    return LaneState(
        name=name,
        tmux_session=tmux_session,
        last_status=last_status,
        last_prompted_at=last_prompted_at,
        prompt_count=prompt_count,
        last_prompt_kind=last_prompt_kind,
        continue_count=continue_count,
        last_failure_reason=last_failure_reason,
        last_failure_exit_code=last_failure_exit_code,
        last_failure_stderr_summary=last_failure_stderr_summary,
        last_failure_record_id=last_failure_record_id,
        last_failed_at=last_failed_at,
        failure_count=failure_count,
        decision_timeout_request_id=decision_timeout_request_id,
        decision_timeout_alerted_at=decision_timeout_alerted_at,
        decision_timeout_seconds=decision_timeout_seconds,
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
