"""CLI runner for the read-only Codex supervisor."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
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


def _handle_research_command(args: argparse.Namespace, *, api) -> int:
    flow = ResearchFlow.in_process(
        Path(args.root),
        provider=FakeResearchProvider(),
    )
    payload = flow.search(args.query).to_dict()
    if args.json:
        _print_json(payload)
    else:
        research = payload.get("research") or {}
        print("[Codex Supervisor Research]")
        print(f"status: {payload['status']}")
        print(f"query: {research.get('query') or payload.get('query', '')}")
        print(f"evidence: {research.get('evidence_status', '')}")
        error = payload.get("error")
        if isinstance(error, dict):
            print(f"retryable: {str(error.get('retryable', False)).lower()}")
            print(f"error: {error.get('message', '')}")
        _print_research_artifacts_plain(payload)
    return 0


_COMMAND_HANDLERS = {
    "dashboard": _handle_dashboard_command,
    "integration-review": _handle_integration_review_command,
    "merge-work-order": _handle_merge_work_order_command,
    "goal": _handle_goal_command,
    "cleanup": _handle_cleanup_command,
    "capacity": _handle_capacity_command,
    "context": _handle_context_command,
    "decision": _handle_decision_command,
    "memory": _handle_memory_command,
    "research": _handle_research_command,
    "replan": _handle_replan_command,
    "state": _handle_state_command,
    "worker-event": _handle_worker_event_command,
    "worker-manager": _handle_worker_manager_command,
}


def _run_cli_impl(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            _print_report(args)
            return 0
        if args.command in _COMMAND_HANDLERS:
            return _COMMAND_HANDLERS[args.command](args, api=sys.modules[__name__])
        if args.command == "advise":
            _validate_execution_modes(args)
            _print_advice(args)
            return 0
        if args.command == "supervise":
            _validate_execution_modes(args)
            _run_supervise(args)
            return 0
        if args.command == "loop":
            _normalize_loop_execution_mode(args)
            _validate_execution_modes(args)
            _run_supervise(args)
            return 0
        if args.command == "up":
            payload = _up_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_daemon_plain(payload)
            return 0
        if args.command in {"check", "overnight-check"}:
            payload = _overnight_check_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_overnight_check_plain(payload)
            return 0
        if args.command == "daemon":
            if (
                args.daemon_command == "watcher"
                and args.watcher_command == "run"
            ):
                _run_daemon_watcher(args)
                return 0
            payload = _daemon_payload(args)
            if args.json:
                _print_json(payload)
            elif args.daemon_command == "watcher":
                _print_watcher_plain(payload)
            else:
                _print_daemon_plain(payload)
            return 0
        if args.command == "watch":
            if args.interval <= 0:
                raise ValueError("interval must be positive")
            if args.iterations is not None and args.iterations <= 0:
                raise ValueError("iterations must be positive")
            iterations = args.iterations
            count = 0
            previous_fingerprint: tuple[object, ...] | None = None
            previous_bell_fingerprint: tuple[object, ...] | None = None
            while iterations is None or count < iterations:
                printed, previous_fingerprint, previous_bell_fingerprint = _print_report(
                    args,
                    previous_fingerprint=previous_fingerprint,
                    previous_bell_fingerprint=previous_bell_fingerprint,
                )
                if printed and iterations is not None and count + 1 < iterations:
                    print()
                count += 1
                if iterations is None or count < iterations:
                    _sleep(args.interval)
            return 0
        if args.command == "web":
            _run_web(args)
            return 0
        if args.command == "launch":
            record = launch_managed_codex(
                codex_home=Path(args.codex_home),
                cwd=Path(args.cwd),
                name=args.name,
                prompt=args.prompt,
                codex_bin=args.codex_bin,
                codex_model=args.codex_model,
                codex_config=tuple(args.codex_config),
                backend=args.backend,
                tmux_session=args.tmux_session,
                worker_role=getattr(args, "worker_role", "worker"),
                popen=subprocess.Popen,
                run=subprocess.run,
            )
            if args.json:
                _print_json({"status": "ok", "managed": record.to_dict()})
            else:
                print(f"已启动托管 Codex：{record.name}")
                print(f"pid：{record.pid}")
                print(f"日志：{record.log_path}")
            return 0
        if args.command == "worker-review":
            payload = collect_worker_reviews(codex_home=Path(args.codex_home))
            if args.json:
                _print_json(payload)
            else:
                print(render_worker_review_plain(payload))
            return 0
        if args.command == "trace":
            payload = _lifecycle_trace_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_lifecycle_trace_plain(payload)
            return 0
        if args.command == "resume":
            record = resume_managed_codex(
                codex_home=Path(args.codex_home),
                cwd=Path(args.cwd),
                name=args.name,
                prompt=args.prompt,
                session_id=args.session_id,
                last=args.last,
                codex_bin=args.codex_bin,
                codex_model=args.codex_model,
                codex_config=tuple(args.codex_config),
                popen=subprocess.Popen,
            )
            if args.json:
                _print_json({"status": "ok", "managed": record.to_dict()})
            else:
                print(f"已恢复托管 Codex：{record.name}")
                target = "--last" if record.resume_last else record.resume_session_id
                print(f"session：{target}")
                print(f"pid：{record.pid}")
                print(f"日志：{record.log_path}")
            return 0
        if args.command == "adopt":
            record = adopt_tmux_session(
                codex_home=Path(args.codex_home),
                cwd=Path(args.cwd),
                name=args.name,
                tmux_session=args.tmux_session,
                prompt=args.prompt,
                run=subprocess.run,
            )
            if args.json:
                _print_json({"status": "ok", "managed": record.to_dict()})
            else:
                print(f"已接管 tmux 会话：{record.name}")
                print(f"tmux：{record.tmux_session}")
            return 0
        if args.command == "discover":
            payload = _discover_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_discover_plain(payload)
            return 0
        if args.command == "archive":
            record = archive_managed_codex(
                codex_home=Path(args.codex_home),
                name=args.name,
            )
            if args.json:
                _print_json({"status": "ok", "managed": record.to_dict()})
            else:
                print(f"已归档托管 Codex：{record.name}")
                if record.tmux_session:
                    print(f"tmux：{record.tmux_session}")
            return 0
        if args.command == "send":
            result = send_to_managed_codex(
                codex_home=Path(args.codex_home),
                name=args.name,
                text=args.text,
                run=subprocess.run,
            )
            if args.json:
                _print_json(
                    {
                        "status": "ok",
                        "text": result.text,
                        "managed": {
                            "name": result.record.name,
                            "record_id": result.record.record_id,
                            "tmux_session": result.record.tmux_session,
                        },
                    }
                )
            else:
                print(f"已发送到托管 Codex：{result.record.name}")
                print(f"tmux：{result.record.tmux_session}")
                print(f"内容：{result.text}")
            return 0
        if args.command == "repair-hooks":
            repairs = repair_tmux_bell_hooks(
                codex_home=Path(args.codex_home),
                run=subprocess.run,
            )
            if args.json:
                _print_json(
                    {
                        "status": "ok",
                        "repairs": [repair.to_dict() for repair in repairs],
                    }
                )
            else:
                if not repairs:
                    print("没有需要修复的托管 tmux 会话。")
                for repair in repairs:
                    print(
                        f"{repair.tmux_session} / {repair.name}: {repair.status}"
                        + (f" / {repair.message}" if repair.message else "")
                    )
            return 0
        if args.command == "start-here":
            payload = _start_here_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_start_here_plain(payload)
            return 0
        if args.command == "guide":
            payload = _guide_payload(args)
            if args.json:
                _print_json(payload)
            else:
                _print_guide_plain(payload)
            return 0
    except KeyboardInterrupt:
        return 130
    except ValueError as exc:
        if getattr(args, "json", False):
            _print_json(
                {
                    "status": "error",
                    "error": {
                        "code": "codex_supervisor_runner_error",
                        "message": str(exc),
                    },
                }
            )
        else:
            print(f"error: {exc}")
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


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


def _run_supervise(args: argparse.Namespace) -> None:
    if args.interval <= 0:
        raise ValueError("interval must be positive")
    if args.iterations is not None and args.iterations <= 0:
        raise ValueError("iterations must be positive")
    decision_timeout = getattr(
        args,
        "decision_timeout",
        DEFAULT_DECISION_TIMEOUT_SECONDS,
    )
    if decision_timeout < 0:
        raise ValueError("decision_timeout must be zero or positive")
    iterations = args.iterations
    count = 0
    previous_fingerprint: tuple[object, ...] | None = None
    previous_bell_fingerprint: tuple[object, ...] | None = None
    while iterations is None or count < iterations:
        auto_adopted = _auto_adopt_discovered_tmux_sessions(args)
        auto_retried_workers = _auto_retry_exited_process_workers(args)
        report = _scan_report(args)
        goal_updates = _sync_goal_lifecycle(args, report)
        merge_promotions = _auto_promote_done_merge_workers_to_main(args)
        cleanup_archived = _auto_archive_done_merge_workers(args)
        cleanup_deleted_worktrees = _auto_delete_archived_worktrees_after_cleanup(
            args,
            cleanup_archived=cleanup_archived,
        )
        decision_timeout_alerts = mark_stale_decision_request_timeouts(
            codex_home=Path(args.codex_home),
            timeout_seconds=decision_timeout,
            webhook_url=getattr(args, "webhook_url", None),
            webhook_secret=getattr(args, "webhook_secret", None),
        )
        fingerprint = _report_fingerprint(report)
        report_changed = previous_fingerprint != fingerprint
        precomputed_auto_action: dict[str, Any] | None = None
        precomputed_executed: dict[str, Any] | None = None
        precomputed_payload: dict[str, Any] | None = None
        force_print = False
        if args.changes_only and not report_changed:
            if args.llm_execute:
                precomputed_payload = _supervise_payload(
                    args,
                    report,
                    iteration=count + 1,
                    auto_adopted=auto_adopted,
                    auto_retried_workers=auto_retried_workers,
                    goal_updates=goal_updates,
                    merge_promotions=merge_promotions,
                    cleanup_archived=cleanup_archived,
                    cleanup_deleted_worktrees=cleanup_deleted_worktrees,
                    decision_timeout_alerts=decision_timeout_alerts,
                )
                force_print = _executed_action_forces_print(
                    precomputed_payload.get("executed", {})
                )
            elif args.auto_execute:
                precomputed_auto_action = _auto_execute_action(
                    report,
                    target_name=args.name,
                    codex_home=Path(args.codex_home),
                    prompt_cooldown_seconds=args.prompt_cooldown,
                    max_continue_count=args.max_continue_count,
                )
                precomputed_executed = _execute_auto_action(
                    args,
                    report,
                    precomputed_auto_action,
                )
                force_print = _executed_action_forces_print(precomputed_executed)
        should_print = (
            not args.changes_only
            or report_changed
            or force_print
            or bool(auto_adopted)
            or bool(auto_retried_workers)
            or bool(goal_updates)
            or bool(merge_promotions)
            or bool(cleanup_archived)
            or bool(cleanup_deleted_worktrees)
            or bool(decision_timeout_alerts)
        )
        if should_print:
            payload = precomputed_payload or _supervise_payload(
                args,
                report,
                iteration=count + 1,
                auto_adopted=auto_adopted,
                auto_retried_workers=auto_retried_workers,
                precomputed_auto_action=precomputed_auto_action,
                precomputed_executed=precomputed_executed,
                goal_updates=goal_updates,
                merge_promotions=merge_promotions,
                cleanup_archived=cleanup_archived,
                cleanup_deleted_worktrees=cleanup_deleted_worktrees,
                decision_timeout_alerts=decision_timeout_alerts,
            )
            bell_fingerprint = _supervise_bell_fingerprint(report, payload)
            if (
                args.bell
                and bell_fingerprint is not None
                and bell_fingerprint != previous_bell_fingerprint
            ):
                _emit_terminal_bell()
            if args.json:
                _print_json(payload)
            else:
                _print_supervise_plain(payload, report)
            if iterations is not None and count + 1 < iterations:
                print()
            previous_bell_fingerprint = bell_fingerprint
        previous_fingerprint = fingerprint
        count += 1
        if iterations is None or count < iterations:
            _sleep(args.interval)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


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


def _supervise_payload(
    args: argparse.Namespace,
    report: Any,
    *,
    iteration: int,
    auto_adopted: list[dict[str, str]] | None = None,
    auto_retried_workers: list[dict[str, Any]] | None = None,
    goal_updates: list[dict[str, Any]] | None = None,
    merge_promotions: list[dict[str, Any]] | None = None,
    cleanup_archived: list[dict[str, Any]] | None = None,
    cleanup_deleted_worktrees: list[dict[str, Any]] | None = None,
    decision_timeout_alerts: list[dict[str, Any]] | None = None,
    precomputed_auto_action: dict[str, Any] | None = None,
    precomputed_executed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = _build_supervise_base_payload(
        args,
        report,
        iteration=iteration,
        auto_adopted=auto_adopted,
        auto_retried_workers=auto_retried_workers,
        goal_updates=goal_updates,
        merge_promotions=merge_promotions,
        cleanup_archived=cleanup_archived,
        cleanup_deleted_worktrees=cleanup_deleted_worktrees,
        decision_timeout_alerts=decision_timeout_alerts,
    )
    payload = base.payload
    action_report = base.action_report
    active_goals = base.active_goals
    explicit_goal = base.explicit_goal
    goal_replenishment = base.goal_replenishment
    worker_reviews: dict[str, Any] | None = None
    if args.llm_action or args.llm_execute:
        llm_context = _planner_context_payload(
            args,
            report,
            action_report=action_report,
            active_goals=active_goals,
            explicit_goal=explicit_goal,
        )
        payload.update(llm_context)
        worker_reviews = llm_context["worker_reviews"]
    planning = _append_supervise_planning_payload(
        args,
        payload,
        report,
        active_goals=active_goals,
        goal_updates=goal_updates,
        goal_replenishment=goal_replenishment,
        worker_reviews=worker_reviews,
    )
    fanout_status = planning.fanout_status
    fanout_paused = planning.fanout_paused
    worker_role_guard = planning.worker_role_guard
    merge_dispatch = planning.merge_dispatch
    fanout_plan = planning.fanout_plan
    if args.llm_summary:
        payload["llm_summary"] = _summarize_with_llm(report)
    _append_supervise_llm_action(
        args,
        payload,
        action_report,
        active_goals=active_goals,
        explicit_goal=explicit_goal,
        fanout_status=fanout_status,
        fanout_paused=fanout_paused,
        worker_role_guard=worker_role_guard,
        merge_dispatch=merge_dispatch,
        fanout_plan=fanout_plan,
    )
    _append_supervise_execution(
        args,
        payload,
        report,
        action_report=action_report,
        active_goals=active_goals,
        goal_replenishment=goal_replenishment,
        worker_reviews=worker_reviews,
        fanout_status=fanout_status,
        fanout_paused=fanout_paused,
        worker_role_guard=worker_role_guard,
        merge_dispatch=merge_dispatch,
        fanout_plan=fanout_plan,
        precomputed_auto_action=precomputed_auto_action,
        precomputed_executed=precomputed_executed,
    )
    _append_supervise_final_payload(args, payload)
    return payload

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
