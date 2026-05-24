"""CLI runner for the read-only Codex supervisor."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from isotope.capabilities.runner import CapabilityRunner
from ..research.flow import ResearchFlow
from ..research.providers import FakeResearchProvider
from ..research.runner import print_artifacts_plain as _print_research_artifacts_plain
from .context import read_recent_context_results, request_project_context
from .decision_requests import (
    DEFAULT_DECISION_TIMEOUT_SECONDS,
    archive_decision_request,
    mark_stale_decision_request_timeouts,
    read_active_decision_requests,
    read_recent_decision_answers,
    record_decision_answer,
    record_decision_request,
)
from .flow import (
    CodexSupervisorFlow,
    _managed_process_log_excerpt,
    _pid_is_running,
    _supervisor_protocol_from_text,
    _terminal_has_active_work_marker,
    _tmux_capture_pane,
    render_plain_report,
)
from .fanout import (
    DEFAULT_FANOUT_LIMIT,
    build_fanout_launch_plan,
)
from .goal_queue import (
    GOAL_STATUS_VALUES,
    archive_supervisor_goal,
    build_supervisor_goal_queue_view,
    read_latest_supervisor_goal_statuses,
    read_active_supervisor_goals,
    record_supervisor_goal,
    record_supervisor_goal_status,
)
from ...agents.scheduler.goal_queue import (
    active_goal_is_deferred,
    filter_replenishment_counted_goals,
)
from .goal_planner import plan_supervisor_goals
from .integration_review import (
    collect_integration_reviews,
    review_managed_record_integration,
)
from .lane_state import (
    DEFAULT_MAX_CONTINUE_COUNT,
    DEFAULT_PROMPT_COOLDOWN_SECONDS,
    default_lane_state_path,
    continue_budget_state,
    lane_failure_state,
    prompt_cooldown_state,
    read_lane_states,
    record_lane_failure,
    record_lane_prompt,
    record_worker_retry,
)
from .llm_summary import (
    generate_llm_action_decision,
    generate_llm_summary,
    resolve_summary_provider_from_env,
)
from .merge_dispatch import (
    DEFAULT_TARGET_NAME as MERGE_DISPATCH_TARGET_NAME,
    merge_dispatch_already_running_action as _merge_dispatch_already_running_action,
    merge_dispatch_already_running_executed as _merge_dispatch_already_running_executed,
    merge_dispatch_planned_executed as _merge_dispatch_planned_executed,
)
from .merge_promotion import (
    check_main_promotion_preconditions as _check_main_promotion_preconditions,
    ci_run_is_terminal as _ci_run_is_terminal,
    ci_run_succeeded as _ci_run_succeeded,
    git_text as _git_text,
    latest_ci_run_for_ref as _latest_ci_run_for_ref,
    merge_promotion_decision_intent as _merge_promotion_decision_intent,
    merge_promotion_repair_prompt as _merge_promotion_repair_prompt,
    run_checked as _run_checked,
    view_ci_run as _view_ci_run,
)
from .merge_repair import (
    blocked_merge_worker_cwd as _blocked_merge_worker_cwd,
    merge_dispatch_conflict_repair_prompt as _merge_dispatch_conflict_repair_prompt,
)
from .notifications import (
    notify_merge_worker_auto_archived,
    notify_worker_integration_review_passed,
)
from .registry import (
    adopt_tmux_session,
    archive_managed_codex,
    default_registry_path,
    launch_managed_codex,
    read_managed_records,
    read_managed_record_events,
    repair_tmux_bell_hooks,
    resume_managed_codex,
    send_to_managed_codex,
)
from .state.projection import build_supervisor_state_snapshot
from .worker_review import collect_worker_reviews, render_worker_review_plain
from .work_order_builder import build_launch_work_order_prompt
from .compat_api import *  # noqa: F403 - legacy runner helper re-exports
from .commands.dispatch import (
    COMMAND_HANDLERS as _COMMAND_HANDLERS,
    handle_research_command as _handle_research_command,
    run_cli_impl as _run_cli_impl,
)
from .constants import *  # noqa: F403 - legacy runner constant re-exports
from .supervise.fingerprint import (
    attention_bell_fingerprint as _attention_bell_fingerprint,
    report_fingerprint as _report_fingerprint,
    status_evidence_fingerprint as _status_evidence_fingerprint,
    supervise_bell_fingerprint as _supervise_bell_fingerprint,
)
from .supervise.goal_lifecycle import (
    goal_status_from_session as _goal_status_from_session,
    non_empty_text as _non_empty_text,
    record_goal_status_from_session as _record_goal_status_from_session,
    sync_goal_lifecycle as _sync_goal_lifecycle,
)
from .supervise.loop import (
    run_supervise as _run_supervise,
    sleep as _sleep,
)
from .supervise.payload import supervise_payload as _supervise_payload
from .web_runner import run_web as _run_web


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _json_object_arg(raw: str | None, field_name: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be a JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    return _run_cli(argv)


def _print_report(
    args: argparse.Namespace,
    *,
    previous_fingerprint: tuple[object, ...] | None = None,
    previous_bell_fingerprint: tuple[object, ...] | None = None,
) -> tuple[bool, tuple[object, ...], tuple[object, ...] | None]:
    flow = CodexSupervisorFlow(codex_home=Path(args.codex_home))
    report = flow.scan(
        limit=args.limit,
        stale_after_seconds=args.stale_after,
        active_within_seconds=args.active_within,
    )
    fingerprint = _report_fingerprint(report)
    if getattr(args, "changes_only", False) and previous_fingerprint == fingerprint:
        return False, fingerprint, previous_bell_fingerprint
    bell_fingerprint = _attention_bell_fingerprint(report)
    if (
        getattr(args, "bell", False)
        and bell_fingerprint is not None
        and bell_fingerprint != previous_bell_fingerprint
    ):
        _emit_terminal_bell()
    if args.json:
        payload = report.to_dict()
        if args.llm_summary:
            payload["llm_summary"] = _summarize_with_llm(report)
        _print_json(payload)
    else:
        print(render_plain_report(report))
        if args.llm_summary:
            print()
            print("[LLM 摘要]")
            print(_summarize_with_llm(report))
    return True, fingerprint, bell_fingerprint


def _scan_report(args: argparse.Namespace) -> Any:
    _sync_managed_worker_failures(
        codex_home=Path(args.codex_home),
        max_run_minutes=getattr(args, "max_run_minutes", 0),
    )
    needs_tmux_pane = (
        getattr(args, "command", None) == "dashboard"
        or bool(getattr(args, "auto_execute", False))
        or bool(getattr(args, "llm_action", False))
        or bool(getattr(args, "llm_execute", False))
    )
    command = getattr(args, "command", None)
    needs_bell_hook_health = command in {"scan", "dashboard", "watch"}
    flow = CodexSupervisorFlow(
        codex_home=Path(args.codex_home),
        tmux_bell_hook_checker=None
        if needs_bell_hook_health
        else _unknown_tmux_bell_hook,
        tmux_pane_reader=_tmux_capture_pane if needs_tmux_pane else None,
    )
    return flow.scan(
        limit=args.limit,
        stale_after_seconds=args.stale_after,
        active_within_seconds=args.active_within,
    )

def _unknown_tmux_bell_hook(_session: str) -> None:
    return None


def _validate_execution_modes(args: argparse.Namespace) -> None:
    if getattr(args, "max_continue_count", 0) < 0:
        raise ValueError("max_continue_count must be zero or positive")
    if getattr(args, "max_context_requests", 0) < 0:
        raise ValueError("max_context_requests must be zero or positive")
    if getattr(args, "max_failure_retries", DEFAULT_MAX_FAILURE_RETRIES) < 0:
        raise ValueError("max_failure_retries must be zero or positive")
    if getattr(args, "max_run_minutes", 0) < 0:
        raise ValueError("max_run_minutes must be zero or positive")
    if getattr(args, "max_worker_retry_count", DEFAULT_MAX_WORKER_RETRY_COUNT) < 0:
        raise ValueError("max_worker_retry_count must be zero or positive")
    if getattr(args, "max_fanout_launches", 1) <= 0:
        raise ValueError("max_fanout_launches must be positive")
    if getattr(args, "goal_low_water", 0) < 0:
        raise ValueError("goal_low_water must be zero or positive")
    if getattr(args, "goal_replenish_limit", 1) <= 0:
        raise ValueError("goal_replenish_limit must be positive")
    modes = [
        name
        for name, enabled in (
            ("execute", bool(args.execute)),
            ("auto_execute", bool(getattr(args, "auto_execute", False))),
            ("llm_execute", bool(args.llm_execute)),
        )
        if enabled
    ]
    if len(modes) > 1:
        raise ValueError("execute, auto_execute, and llm_execute cannot be used together")


def _normalize_loop_execution_mode(args: argparse.Namespace) -> None:
    if getattr(args, "rule_execute", False):
        args.auto_execute = True
        args.llm_execute = False
        args.llm_action = False


def _maybe_replenish_active_goals(
    args: argparse.Namespace,
    active_goals: list[dict[str, Any]],
    *,
    running_target_names: set[str] | None = None,
) -> dict[str, Any] | None:
    if getattr(args, "command", None) != "loop":
        return None
    low_water = getattr(args, "goal_low_water", 0)
    if low_water <= 0:
        return None
    if getattr(args, "name", None) or _explicit_goal_text(args):
        return None
    active_before = len(
        _replenishment_counted_active_goals(
            active_goals,
            running_target_names=running_target_names,
        )
    )
    if active_before >= low_water:
        return None

    replenish_limit = min(
        getattr(args, "goal_replenish_limit", DEFAULT_FANOUT_LIMIT),
        low_water - active_before,
    )
    root = _workspace_root(args) or Path.cwd().resolve()
    try:
        provider = resolve_summary_provider_from_env(agent_name="supervisor")
        plan = plan_supervisor_goals(
            root=root,
            codex_home=Path(args.codex_home),
            provider=provider,
            user_goal=_goal_replenishment_prompt(args),
            write=True,
            limit=replenish_limit,
            planning_trigger="low_water",
        )
    except Exception as exc:
        return {
            "status": "error",
            "trigger": "low_water",
            "active_before": active_before,
            "active_total_before": len(active_goals),
            "low_water": low_water,
            "requested_limit": replenish_limit,
            "root": str(root),
            "reason": str(exc),
        }
    written_goals = plan.get("written_goals") if isinstance(plan, dict) else []
    if not isinstance(written_goals, list):
        written_goals = []
    parallel_recommendations = (
        plan.get("parallel_recommendations") if isinstance(plan, dict) else []
    )
    if not isinstance(parallel_recommendations, list):
        parallel_recommendations = []
    return {
        "status": "ok",
        "trigger": "low_water",
        "active_before": active_before,
        "active_total_before": len(active_goals),
        "low_water": low_water,
        "requested_limit": replenish_limit,
        "root": str(root),
        "written_count": len(written_goals),
        "written_goals": written_goals,
        "plan_summary": plan.get("plan_summary") if isinstance(plan, dict) else None,
        "parallel_recommendations": parallel_recommendations,
    }


def _goal_replenishment_prompt(args: argparse.Namespace) -> str:
    raw = getattr(args, "goal_replenish_prompt", None)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return DEFAULT_GOAL_REPLENISH_PROMPT


def _replenishment_counted_active_goals(
    active_goals: list[dict[str, Any]],
    *,
    running_target_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    return filter_replenishment_counted_goals(
        active_goals,
        running_target_names=running_target_names or set(),
    )


def _active_goal_is_deferred(goal: dict[str, Any]) -> bool:
    return active_goal_is_deferred(goal)


def _selected_active_goal(args: argparse.Namespace) -> dict[str, Any] | None:
    goals = _active_goal_dicts(args, limit=1)
    return goals[0] if goals else None


def _emit_terminal_bell() -> None:
    sys.stderr.write("\a")
    sys.stderr.flush()


def _notify_integration_review_webhooks(
    args: argparse.Namespace,
    payload: dict[str, Any],
) -> None:
    webhook_url = getattr(args, "webhook_url", None)
    if not isinstance(webhook_url, str) or not webhook_url.strip():
        return
    groups = payload.get("groups")
    if not isinstance(groups, dict):
        return
    for group in ("ready_to_integrate", "already_integrated"):
        items = groups.get(group)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            protocol = item.get("supervisor_protocol")
            if not isinstance(protocol, dict):
                continue
            status = protocol.get("status")
            if not isinstance(status, str) or status.lower() != "done":
                continue
            record_id = item.get("record_id")
            if not isinstance(record_id, str) or not record_id.strip():
                continue
            notify_worker_integration_review_passed(
                record_id=record_id,
                group=group,
                status="done",
                webhook_url=webhook_url,
                webhook_secret=getattr(args, "webhook_secret", None),
            )


def _promote_llm_command_suggestion(payload: dict[str, Any]) -> None:
    action = payload.get("llm_action")
    if not isinstance(action, dict):
        return
    if "command_suggestion" not in action:
        return
    if "rule_command_suggestion" not in payload:
        payload["rule_command_suggestion"] = payload.get("command_suggestion")
    payload["command_suggestion"] = action.get("command_suggestion")


def _summarize_with_llm(report: Any) -> str:
    provider = resolve_summary_provider_from_env(agent_name="supervisor")
    return generate_llm_summary(report, provider)


def _recent_context_results(args: argparse.Namespace, report: Any) -> list[dict[str, Any]]:
    cwd = _context_cwd_for_report(report) or _goal_workspace(args)
    results = read_recent_context_results(
        codex_home=Path(args.codex_home),
        cwd=Path(cwd) if cwd else None,
    )
    return [result.to_dict() for result in results]


def _decision_request_dicts(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        request.to_dict()
        for request in read_active_decision_requests(codex_home=Path(args.codex_home))
    ]


def _decision_answer_dicts(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        dict(answer)
        for answer in read_recent_decision_answers(codex_home=Path(args.codex_home))
    ]


def _worker_review_context(args: argparse.Namespace) -> dict[str, Any]:
    return collect_worker_reviews(codex_home=Path(args.codex_home), lightweight=True)


def _active_goal_dicts(
    args: argparse.Namespace,
    *,
    limit: int = 20,
    include_status: bool = False,
) -> list[dict[str, Any]]:
    return _active_goal_dicts_for_codex_home(
        Path(args.codex_home),
        limit=limit,
        include_status=include_status,
    )


def _active_goal_dicts_for_codex_home(
    codex_home: Path,
    *,
    limit: int = 20,
    include_status: bool = False,
) -> list[dict[str, Any]]:
    statuses = (
        read_latest_supervisor_goal_statuses(codex_home=codex_home)
        if include_status
        else {}
    )
    return [
        _goal_dict_with_status(goal.to_dict(), statuses)
        for goal in read_active_supervisor_goals(
            codex_home=codex_home,
            limit=limit,
        )
    ]


def _goal_dict_with_status(
    goal: dict[str, Any],
    statuses: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    status = statuses.get(goal.get("goal_id"))
    if not status:
        return goal
    merged = {**goal}
    for key, value in status.items():
        if key != "goal_id":
            merged[key] = value
    return merged


if __name__ == "__main__":
    raise SystemExit(main())
