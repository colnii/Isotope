"""Rule-based auto action selection for Supervisor loops."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from isotope.features.supervisor.lane_state import (
    DEFAULT_MAX_CONTINUE_COUNT,
    DEFAULT_PROMPT_COOLDOWN_SECONDS,
    continue_budget_state,
    prompt_cooldown_state,
)

DEFAULT_MAX_RUN_MINUTES = 0


def execute_auto_action(
    args: argparse.Namespace,
    report: Any,
    auto_action: dict[str, Any],
    *,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    if auto_action["kind"] in api.EXECUTABLE_ADVICE_KINDS:
        return api._execute_advice(
            args,
            report,
            {},
            kind=auto_action["kind"],
            target_name=auto_action.get("target_name"),
        )
    return {
        "kind": auto_action["kind"],
        "skipped": True,
        "reason": auto_action["reason"],
    }


def executed_action_forces_print(executed: dict[str, Any]) -> bool:
    if executed.get("kind") == "ask_user":
        return True
    return executed.get("kind") != "monitor" and not executed.get("skipped")


def auto_execute_action(
    report: Any,
    *,
    target_name: str | None = None,
    codex_home: Path | None = None,
    prompt_cooldown_seconds: int = DEFAULT_PROMPT_COOLDOWN_SECONDS,
    max_continue_count: int = DEFAULT_MAX_CONTINUE_COUNT,
    max_run_minutes: int = DEFAULT_MAX_RUN_MINUTES,
    api: Any | None = None,
) -> dict[str, str]:
    if api is None:
        from isotope.features.supervisor import runner as api

    if target_name:
        managed = api._managed_tmux_session_by_name(report, target_name)
        if managed is None:
            return {
                "kind": "monitor",
                "reason": f"managed lane not found: {target_name}",
            }
        action = auto_execute_action_for_managed(report, managed, api=api)
        if auto_action_exhausts_continue_budget(
            action,
            codex_home=codex_home,
            managed=managed,
            max_continue_count=max_continue_count,
        ):
            return {
                "kind": "monitor",
                "reason": "lane continue budget exhausted",
                "target_name": managed.managed_name or target_name,
            }
        if auto_action_exhausts_run_budget(
            action,
            codex_home=codex_home,
            managed=managed,
            max_run_minutes=max_run_minutes,
            api=api,
        ):
            return {
                "kind": "monitor",
                "reason": "lane run budget exhausted",
                "target_name": managed.managed_name or target_name,
            }
        return action
    managed_lanes = [
        session
        for session in report.sessions
        if api._is_active_managed_tmux_session(session)
    ]
    if not managed_lanes:
        return {
            "kind": "monitor",
            "reason": "no managed tmux lane",
        }
    include_target_name = len(managed_lanes) > 1
    candidates: list[tuple[dict[str, str], Any]] = []
    for managed in managed_lanes:
        action = auto_execute_action_for_managed(report, managed, api=api)
        if include_target_name and managed.managed_name:
            action = {**action, "target_name": managed.managed_name}
        candidates.append((action, managed))
    cooldown_candidates: list[dict[str, str]] = []
    continue_budget_candidates: list[dict[str, str]] = []
    for action, managed in candidates:
        if action["kind"] not in api.EXECUTABLE_ADVICE_KINDS:
            continue
        if auto_action_exhausts_continue_budget(
            action,
            codex_home=codex_home,
            managed=managed,
            max_continue_count=max_continue_count,
        ):
            continue_budget_candidates.append(
                {
                    "kind": "monitor",
                    "reason": "lane continue budget exhausted",
                    **({"target_name": managed.managed_name} if managed.managed_name else {}),
                }
            )
            continue
        if auto_action_exhausts_run_budget(
            action,
            codex_home=codex_home,
            managed=managed,
            max_run_minutes=max_run_minutes,
            api=api,
        ):
            continue_budget_candidates.append(
                {
                    "kind": "monitor",
                    "reason": "lane run budget exhausted",
                    **({"target_name": managed.managed_name} if managed.managed_name else {}),
                }
            )
            continue
        if auto_action_in_prompt_cooldown(
            codex_home=codex_home,
            managed=managed,
            prompt_cooldown_seconds=prompt_cooldown_seconds,
        ):
            cooldown_candidates.append(action)
            continue
        return action
    for action, _managed in candidates:
        if action["reason"] == "lane needs human attention":
            return action
    if cooldown_candidates:
        return cooldown_candidates[0]
    if continue_budget_candidates:
        return continue_budget_candidates[0]
    return candidates[0][0]


def auto_action_exhausts_continue_budget(
    action: dict[str, str],
    *,
    codex_home: Path | None,
    managed: Any,
    max_continue_count: int,
) -> bool:
    if (
        action["kind"] != "send_continue"
        or codex_home is None
        or not managed.managed_name
    ):
        return False
    return (
        continue_budget_state(
            codex_home=codex_home,
            name=managed.managed_name,
            max_continue_count=max_continue_count,
        )
        is not None
    )


def auto_action_exhausts_run_budget(
    action: dict[str, str],
    *,
    codex_home: Path | None,
    managed: Any,
    max_run_minutes: int,
    api: Any | None = None,
) -> bool:
    if api is None:
        from isotope.features.supervisor import runner as api

    if (
        action["kind"] != "send_continue"
        or codex_home is None
        or not managed.managed_name
    ):
        return False
    return (
        api._run_budget_state(
            codex_home=codex_home,
            name=managed.managed_name,
            max_run_minutes=max_run_minutes,
        )
        is not None
    )


def auto_action_in_prompt_cooldown(
    *,
    codex_home: Path | None,
    managed: Any,
    prompt_cooldown_seconds: int,
) -> bool:
    if codex_home is None or not managed.managed_name:
        return False
    return (
        prompt_cooldown_state(
            codex_home=codex_home,
            name=managed.managed_name,
            cooldown_seconds=prompt_cooldown_seconds,
        )
        is not None
    )


def auto_execute_action_for_managed(
    report: Any,
    managed: Any,
    *,
    api: Any | None = None,
) -> dict[str, str]:
    if api is None:
        from isotope.features.supervisor import runner as api

    if managed_terminal_looks_busy(managed, api=api):
        return {
            "kind": "monitor",
            "reason": "managed lane is running without ready signal",
        }
    status_source = auto_status_source(report, managed, api=api)
    supervisor_status = (status_source.supervisor_status or "").lower()
    if supervisor_status in {"blocked", "needs_user"}:
        return {
            "kind": "monitor",
            "reason": "lane needs human attention",
        }
    if supervisor_status == "done":
        if supervisor_next_marks_terminal_done(status_source, api=api):
            return {
                "kind": "monitor",
                "reason": "managed lane reported terminal done",
            }
        return {
            "kind": "send_continue",
            "reason": "managed lane reported done",
        }
    recommendation = report.recommendation
    target_ids = {managed.session_id, status_source.session_id}
    recommendation_targets_lane = recommendation.target_session_id in target_ids
    if (
        recommendation_targets_lane
        and recommendation.action in {"inspect_blocked", "review_user_prompt", "inspect_error"}
    ):
        return {
            "kind": "monitor",
            "reason": "lane needs human attention",
        }
    if recommendation_targets_lane and recommendation.action == "review_done":
        if supervisor_next_marks_terminal_done(status_source, api=api):
            return {
                "kind": "monitor",
                "reason": "managed lane reported terminal done",
            }
        return {
            "kind": "send_continue",
            "reason": "managed lane reported done",
        }
    if status_source.managed_terminal_ready or managed.managed_terminal_ready:
        return {
            "kind": "send_status",
            "reason": "managed terminal is ready for input",
        }
    if (
        status_source.managed_bell
        or managed.managed_bell
        or status_source.status == "stale"
        or (
            recommendation_targets_lane
            and recommendation.action in {"inspect_bell", "inspect_stale"}
        )
    ):
        return {
            "kind": "send_status",
            "reason": f"recommendation is {recommendation.action}",
        }
    if not status_source.supervisor_status:
        return {
            "kind": "monitor",
            "reason": "managed lane is running without ready signal",
        }
    return {
        "kind": "monitor",
        "reason": "lane is still working",
    }


def supervisor_next_marks_terminal_done(session: Any, *, api: Any | None = None) -> bool:
    if api is None:
        from isotope.features.supervisor import runner as api

    next_text = api._normalize_match_text(getattr(session, "supervisor_next", None))
    return any(marker in next_text for marker in api.TERMINAL_DONE_NEXT_MARKERS)


def managed_terminal_looks_busy(session: Any, *, api: Any | None = None) -> bool:
    if api is None:
        from isotope.features.supervisor import runner as api

    text = getattr(session, "managed_terminal_excerpt", None)
    if not isinstance(text, str):
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return api._terminal_has_active_work_marker(lines[-8:])


def auto_status_source(report: Any, managed: Any, *, api: Any | None = None) -> Any:
    if api is None:
        from isotope.features.supervisor import runner as api

    candidates = [
        session
        for session in report.sessions
        if not session.managed
        and (session.status not in {"stale", "exited"} or session.supervisor_status)
    ]
    return api._best_linked_session_for_managed(managed, candidates, set()) or managed
