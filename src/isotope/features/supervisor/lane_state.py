"""Lightweight state for managed Supervisor lanes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from isotope.platform.state.lane_state import SupervisorLaneState


LaneState = SupervisorLaneState

DEFAULT_PROMPT_COOLDOWN_SECONDS = 300
DEFAULT_MAX_CONTINUE_COUNT = 0


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
        worker_retry_count=previous.worker_retry_count if previous is not None else 0,
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
        worker_retry_count=previous.worker_retry_count if previous is not None else 0,
    )
    states[name] = state
    write_lane_states(path, states)
    return state


def record_worker_retry(
    *,
    codex_home: Path | str,
    name: str,
    tmux_session: str | None,
    now: datetime | None = None,
) -> LaneState:
    path = default_lane_state_path(codex_home)
    states = read_lane_states(path)
    current = _ensure_aware_utc(now or _utc_now())
    previous = states.get(name)
    retry_count = previous.worker_retry_count + 1 if previous is not None else 1
    state = LaneState(
        name=name,
        tmux_session=tmux_session,
        last_status="worker_retry",
        last_prompted_at=current.isoformat(),
        prompt_count=(
            previous.prompt_count + 1
            if previous is not None and previous.last_status == "worker_retry"
            else 1
        ),
        last_prompt_kind="worker_retry",
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
        decision_timeout_request_id=(
            previous.decision_timeout_request_id if previous is not None else None
        ),
        decision_timeout_alerted_at=(
            previous.decision_timeout_alerted_at if previous is not None else None
        ),
        decision_timeout_seconds=(
            previous.decision_timeout_seconds if previous is not None else None
        ),
        worker_retry_count=retry_count,
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
        worker_retry_count=previous.worker_retry_count if previous is not None else 0,
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
        worker_retry_count=previous.worker_retry_count,
    )
    states[name] = state
    write_lane_states(path, states)
    return state


def _state_from_dict(raw: dict[str, Any]) -> LaneState | None:
    return LaneState.from_dict(raw)


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
