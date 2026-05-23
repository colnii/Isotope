"""Worker failure synchronization and retry lifecycle helpers."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Any


def sync_managed_worker_failures(
    *,
    codex_home: Path,
    max_run_minutes: int = 0,
    api: Any | None = None,
) -> list[dict[str, Any]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    failures: list[dict[str, Any]] = []
    for record in api.read_managed_records(api.default_registry_path(codex_home)):
        if record.backend == "tmux":
            continue
        failure = managed_worker_failure_from_record(
            record,
            max_run_minutes=max_run_minutes,
            api=api,
        )
        if failure is None:
            continue
        state = api.record_lane_failure(
            codex_home=codex_home,
            name=record.name,
            tmux_session=record.tmux_session,
            reason=failure["reason"],
            exit_code=failure.get("exit_code"),
            stderr_summary=failure.get("stderr_summary"),
            record_id=record.record_id,
        )
        failures.append(state.to_dict())
    return failures


def managed_worker_failure_from_record(
    record: Any,
    *,
    max_run_minutes: int = 0,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    excerpt = api._managed_process_log_excerpt(record.log_path) or ""
    protocol = api._supervisor_protocol_from_text(excerpt)
    if protocol.get("status") in {"done", "blocked", "needs_user"}:
        return None
    is_running = api._pid_is_running(record.pid)
    if not is_running and (parsed := nonzero_exit_failure(excerpt)):
        return parsed
    if max_run_minutes > 0 and managed_record_exceeded_run_budget(
        record,
        max_run_minutes=max_run_minutes,
        api=api,
    ):
        return {
            "reason": "timeout",
            "exit_code": None,
            "stderr_summary": stderr_summary_from_excerpt(excerpt)
            or f"worker exceeded {max_run_minutes} minute run budget",
        }
    return None


def auto_retry_exited_process_workers(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> list[dict[str, Any]]:
    if api is None:
        from isotope.features.supervisor import runner as api

    max_retries = getattr(
        args,
        "max_worker_retry_count",
        api.DEFAULT_MAX_WORKER_RETRY_COUNT,
    )
    if max_retries <= 0:
        return []
    codex_home = Path(args.codex_home)
    latest_by_name: dict[str, Any] = {}
    for record in api.read_managed_records(api.default_registry_path(codex_home)):
        latest_by_name[record.name] = record

    retried: list[dict[str, Any]] = []
    lane_states = api.read_lane_states(api.default_lane_state_path(codex_home))
    for record in latest_by_name.values():
        failure = process_worker_retry_failure(
            record,
            max_run_minutes=getattr(args, "max_run_minutes", 0),
            api=api,
        )
        legacy_working_retry = failure is None and process_worker_needs_retry(
            record,
            api=api,
        )
        if failure is None and not legacy_working_retry:
            continue
        state = (
            api.record_lane_failure(
                codex_home=codex_home,
                name=record.name,
                tmux_session=record.tmux_session,
                reason=str(failure["reason"]),
                exit_code=failure.get("exit_code"),
                stderr_summary=failure.get("stderr_summary"),
                record_id=record.record_id,
            )
            if failure is not None
            else lane_states.get(record.name)
        )
        if failure is not None and failure.get("reason") == "usage_limit":
            ensure_worker_retry_decision_request(
                args,
                record=record,
                state=state,
                failure=failure,
                max_retries=max_retries,
                api=api,
            )
            continue
        retry_count = state.worker_retry_count if state is not None else 0
        if retry_count >= max_retries:
            if failure is not None:
                ensure_worker_retry_decision_request(
                    args,
                    record=record,
                    state=state,
                    failure=failure,
                    max_retries=max_retries,
                    api=api,
                )
            continue
        launched = api.launch_managed_codex(
            codex_home=codex_home,
            cwd=Path(record.cwd),
            name=record.name,
            prompt=record.prompt,
            codex_model=api._worker_codex_model(args),
            codex_config=api._worker_codex_config(args),
            worker_role=record.worker_role,
            popen=subprocess.Popen,
            run=subprocess.run,
        )
        updated_state = api.record_worker_retry(
            codex_home=codex_home,
            name=record.name,
            tmux_session=None,
        )
        retried.append(
            {
                "name": record.name,
                "previous_record_id": record.record_id,
                "record_id": launched.record_id,
                "pid": launched.pid,
                "retry_count": updated_state.worker_retry_count,
                "max_retries": max_retries,
                **({"failure": failure} if failure is not None else {}),
            }
        )
    return retried


def process_worker_retry_failure(
    record: Any,
    *,
    max_run_minutes: int = 0,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if record.backend != "process":
        return None
    if not api._cwd_is_existing_dir(record.cwd):
        return None
    return managed_worker_failure_from_record(
        record,
        max_run_minutes=max_run_minutes,
        api=api,
    )


def ensure_worker_retry_decision_request(
    args: argparse.Namespace,
    *,
    record: Any,
    state: Any,
    failure: dict[str, Any],
    max_retries: int,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if active_worker_retry_decision_exists(
        codex_home=Path(args.codex_home),
        lane_name=record.name,
        api=api,
    ):
        return None
    event = {
        "event_type": "worker_retry_failed",
        "lane_name": record.name,
        "goal_id": None,
        "error_summary": worker_retry_error_summary(failure),
        "retry_count": state.worker_retry_count if state is not None else max_retries,
        "max_retries": max_retries,
        "record_id": record.record_id,
        "failure": failure,
    }
    return api._execute_ask_user_action(
        args,
        api._failure_decision_request_action(
            event=event,
            question=api._failure_question("worker_retry_failed"),
            reason="worker retry limit exceeded",
        ),
    )


def active_worker_retry_decision_exists(
    *,
    codex_home: Path,
    lane_name: str,
    api: Any | None = None,
) -> bool:
    if api is None:
        from isotope.features.supervisor import runner as api

    session_id = f"failure:worker_retry_failed:{lane_name}"
    return any(
        request.session_id == session_id
        for request in api.read_active_decision_requests(
            codex_home=codex_home,
            limit=1000,
        )
    )


def worker_retry_error_summary(failure: dict[str, Any]) -> str:
    reason = str(failure.get("reason") or "worker failed")
    stderr_summary = failure.get("stderr_summary")
    if isinstance(stderr_summary, str) and stderr_summary.strip():
        return f"{reason}: {stderr_summary.strip()}"
    exit_code = failure.get("exit_code")
    if isinstance(exit_code, int):
        return f"{reason}: exit code {exit_code}"
    return reason


def process_worker_needs_retry(record: Any, *, api: Any | None = None) -> bool:
    if api is None:
        from isotope.features.supervisor import runner as api

    if record.backend != "process":
        return False
    if api._pid_is_running(record.pid):
        return False
    if not api._cwd_is_existing_dir(record.cwd):
        return False
    excerpt = api._managed_process_log_excerpt(record.log_path) or ""
    protocol = api._supervisor_protocol_from_text(excerpt)
    status = (protocol.get("status") or "").strip().lower()
    return status == "working"


def managed_record_exceeded_run_budget(
    record: Any,
    *,
    max_run_minutes: int,
    api: Any | None = None,
) -> bool:
    if api is None:
        from isotope.features.supervisor import runner as api

    started_at = api._parse_timestamp(record.started_at)
    if started_at is None:
        return False
    elapsed_seconds = max(0, int((api._utc_now() - started_at).total_seconds()))
    return elapsed_seconds >= max_run_minutes * 60


def nonzero_exit_failure(excerpt: str) -> dict[str, Any] | None:
    usage_limit = usage_limit_failure(excerpt)
    if usage_limit is not None:
        return usage_limit
    for pattern in (
        r"process exited with code\s+(-?\d+)",
        r"exit code\s+(-?\d+)",
        r"exited with status\s+(-?\d+)",
        r"returncode[=:]\s*(-?\d+)",
    ):
        match = re.search(pattern, excerpt, flags=re.IGNORECASE)
        if match is None:
            continue
        exit_code = int(match.group(1))
        if exit_code == 0:
            return None
        return {
            "reason": "exit_code",
            "exit_code": exit_code,
            "stderr_summary": stderr_summary_from_excerpt(excerpt),
        }
    return None


def usage_limit_failure(excerpt: str) -> dict[str, Any] | None:
    lowered = excerpt.lower()
    if (
        "you've hit your usage limit" not in lowered
        and "you have hit your usage limit" not in lowered
    ):
        return None
    return {
        "reason": "usage_limit",
        "exit_code": None,
        "stderr_summary": stderr_summary_from_excerpt(excerpt),
    }


def stderr_summary_from_excerpt(excerpt: str, *, limit: int = 500) -> str | None:
    lines = [line.strip() for line in excerpt.splitlines() if line.strip()]
    stderr_lines = [
        line
        for line in lines
        if line.lower().startswith(("stderr:", "error:", "traceback"))
    ]
    candidates = stderr_lines or [
        line
        for line in lines
        if not line.upper().startswith("SUPERVISOR_")
        and not re.search(
            r"(process exited with code|exit code|exited with status|returncode[=:])",
            line,
            flags=re.IGNORECASE,
        )
    ]
    if not candidates:
        return None
    summary = " / ".join(candidates[-3:])
    return summary[:limit]


def lane_failure_payload(
    *,
    codex_home: Path,
    record: Any,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    state = api.lane_failure_state(codex_home=codex_home, name=record.name)
    if state is None:
        return None
    if (
        state.last_failure_record_id
        and state.last_failure_record_id != record.record_id
    ):
        return None
    return {
        "reason": state.last_failure_reason,
        "exit_code": state.last_failure_exit_code,
        "stderr_summary": state.last_failure_stderr_summary,
        "record_id": state.last_failure_record_id,
    }
