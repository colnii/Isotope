"""Execution helpers for Supervisor command suggestions."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def execute_advice(
    args: argparse.Namespace,
    report: Any,
    payload: dict[str, Any],
    *,
    kind: str | None = None,
    target_name: str | None = None,
    api: Any | None = None,
) -> dict[str, Any]:
    if api is None:
        from isotope.features.supervisor import runner as api

    kind = str(kind or args.execute)
    if kind not in api.EXECUTABLE_ADVICE_KINDS:
        supported = ", ".join(sorted(api.EXECUTABLE_ADVICE_KINDS))
        raise ValueError(f"execute supports only: {supported}")
    explicit_target_name = target_name or args.name
    if explicit_target_name:
        target = api._managed_tmux_session_by_name(report, explicit_target_name)
        if target is None:
            raise ValueError(f"managed lane not found: {explicit_target_name}")
    else:
        target = api._target_session(report, report.recommendation.target_session_id)
        if target is None or not target.managed_name:
            target = api._first_managed_tmux_session(report)
    if target is None or not target.managed_name:
        target = api._first_managed_tmux_session(report)
    if target is None or not target.managed_name:
        raise ValueError(f"no managed tmux target for: {kind}")
    suggestion = suggestion_by_kind(api._managed_tmux_command_suggestions(target), kind)
    if suggestion is None:
        raise ValueError(f"no generated command suggestion for: {kind}")
    if api._managed_terminal_looks_busy(target):
        return {
            "kind": "monitor",
            "skipped": True,
            "reason": "managed lane is running without ready signal",
            "blocked_kind": kind,
            "command": suggestion["command"],
        }
    if kind == "send_continue":
        if budget_state := api.continue_budget_state(
            codex_home=Path(args.codex_home),
            name=target.managed_name,
            max_continue_count=args.max_continue_count,
        ):
            return {
                "kind": kind,
                "command": suggestion["command"],
                "skipped": True,
                "reason": "lane continue budget exhausted",
                "lane_state": budget_state.to_dict(),
            }
        if run_budget := run_budget_state(
            codex_home=Path(args.codex_home),
            name=target.managed_name,
            max_run_minutes=args.max_run_minutes,
            api=api,
        ):
            return {
                "kind": kind,
                "command": suggestion["command"],
                "skipped": True,
                "reason": "lane run budget exhausted",
                "run_budget": run_budget,
            }
    if cooldown_state := api.prompt_cooldown_state(
        codex_home=Path(args.codex_home),
        name=target.managed_name,
        cooldown_seconds=args.prompt_cooldown,
    ):
        return {
            "kind": kind,
            "command": suggestion["command"],
            "skipped": True,
            "reason": "lane prompt cooldown active",
            "lane_state": cooldown_state.to_dict(),
        }
    result = api.send_to_managed_codex(
        codex_home=Path(args.codex_home),
        name=target.managed_name,
        text=api.EXECUTABLE_ADVICE_TEXT[kind],
        run=api.subprocess.run,
    )
    api.record_lane_prompt(
        codex_home=Path(args.codex_home),
        name=result.record.name,
        tmux_session=result.record.tmux_session,
        status=target.supervisor_status or target.status,
        prompt_kind=kind,
    )
    return {
        "kind": kind,
        "command": suggestion["command"],
        "text": result.text,
        "managed": {
            "name": result.record.name,
            "record_id": result.record.record_id,
            "tmux_session": result.record.tmux_session,
        },
    }


def run_budget_state(
    *,
    codex_home: Path,
    name: str,
    max_run_minutes: int,
    api: Any | None = None,
) -> dict[str, Any] | None:
    if api is None:
        from isotope.features.supervisor import runner as api

    if max_run_minutes <= 0:
        return None
    records = [
        record
        for record in api.read_managed_records(api.default_registry_path(codex_home))
        if record.name == name
    ]
    if not records:
        return None
    latest = max(
        records,
        key=lambda record: api._timestamp_sort_value(record.started_at),
    )
    started_at = api._parse_timestamp(latest.started_at)
    if started_at is None:
        return None
    elapsed_seconds = max(0, int((api._utc_now() - started_at).total_seconds()))
    if elapsed_seconds < max_run_minutes * 60:
        return None
    return {
        "name": latest.name,
        "record_id": latest.record_id,
        "started_at": latest.started_at,
        "elapsed_seconds": elapsed_seconds,
        "max_run_minutes": max_run_minutes,
    }


def suggestion_by_kind(
    suggestions: list[dict[str, str]],
    kind: str,
) -> dict[str, str] | None:
    for suggestion in suggestions:
        if suggestion["kind"] == kind:
            return suggestion
    return None
