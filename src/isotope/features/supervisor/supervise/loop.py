"""Supervisor supervise/loop orchestration."""

from __future__ import annotations

import argparse
import time
from typing import Any


def _runner_api(api: Any | None) -> Any:
    if api is not None:
        return api
    from isotope.features.supervisor import runner

    return runner


def run_supervise(
    args: argparse.Namespace,
    *,
    api: Any | None = None,
) -> None:
    api = _runner_api(api)
    if args.interval <= 0:
        raise ValueError("interval must be positive")
    if args.iterations is not None and args.iterations <= 0:
        raise ValueError("iterations must be positive")
    decision_timeout = getattr(
        args,
        "decision_timeout",
        api.DEFAULT_DECISION_TIMEOUT_SECONDS,
    )
    if decision_timeout < 0:
        raise ValueError("decision_timeout must be zero or positive")
    iterations = args.iterations
    count = 0
    previous_fingerprint: tuple[object, ...] | None = None
    previous_bell_fingerprint: tuple[object, ...] | None = None
    while iterations is None or count < iterations:
        auto_adopted = api._auto_adopt_discovered_tmux_sessions(args)
        auto_retried_workers = api._auto_retry_exited_process_workers(args)
        report = api._scan_report(args)
        goal_updates = api._sync_goal_lifecycle(args, report)
        merge_promotions = api._auto_promote_done_merge_workers_to_main(args)
        cleanup_archived = api._auto_archive_done_merge_workers(args)
        cleanup_deleted_worktrees = api._auto_delete_archived_worktrees_after_cleanup(
            args,
            cleanup_archived=cleanup_archived,
        )
        decision_timeout_alerts = api.mark_stale_decision_request_timeouts(
            codex_home=api.Path(args.codex_home),
            timeout_seconds=decision_timeout,
            webhook_url=getattr(args, "webhook_url", None),
            webhook_secret=getattr(args, "webhook_secret", None),
        )
        fingerprint = api._report_fingerprint(report)
        report_changed = previous_fingerprint != fingerprint
        precomputed_auto_action: dict[str, Any] | None = None
        precomputed_executed: dict[str, Any] | None = None
        precomputed_payload: dict[str, Any] | None = None
        force_print = False
        if args.changes_only and not report_changed:
            if args.llm_execute:
                precomputed_payload = api._supervise_payload(
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
                force_print = api._executed_action_forces_print(
                    precomputed_payload.get("executed", {})
                )
            elif args.auto_execute:
                precomputed_auto_action = api._auto_execute_action(
                    report,
                    target_name=args.name,
                    codex_home=api.Path(args.codex_home),
                    prompt_cooldown_seconds=args.prompt_cooldown,
                    max_continue_count=args.max_continue_count,
                )
                precomputed_executed = api._execute_auto_action(
                    args,
                    report,
                    precomputed_auto_action,
                )
                force_print = api._executed_action_forces_print(precomputed_executed)
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
            payload = precomputed_payload or api._supervise_payload(
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
            bell_fingerprint = api._supervise_bell_fingerprint(report, payload)
            if (
                args.bell
                and bell_fingerprint is not None
                and bell_fingerprint != previous_bell_fingerprint
            ):
                api._emit_terminal_bell()
            if args.json:
                api._print_json(payload)
            else:
                api._print_supervise_plain(payload, report)
            if iterations is not None and count + 1 < iterations:
                print()
            previous_bell_fingerprint = bell_fingerprint
        previous_fingerprint = fingerprint
        count += 1
        if iterations is None or count < iterations:
            api._sleep(args.interval)


def sleep(seconds: float) -> None:
    time.sleep(seconds)


__all__ = ("run_supervise", "sleep")
