"""Scan and watch report helpers for the Supervisor CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from isotope.features.supervisor.flow import (
    CodexSupervisorFlow,
    render_plain_report,
)
from isotope.features.supervisor.llm_action.llm_summary import (
    generate_llm_summary,
)
from isotope.features.supervisor.state.constants import DEFAULT_MAX_RUN_MINUTES
from isotope.features.supervisor.supervise.fingerprint import (
    attention_bell_fingerprint,
    report_fingerprint,
)


def print_report(
    args: argparse.Namespace,
    *,
    previous_fingerprint: tuple[object, ...] | None = None,
    previous_bell_fingerprint: tuple[object, ...] | None = None,
    api: Any | None = None,
) -> tuple[bool, tuple[object, ...], tuple[object, ...] | None]:
    if api is None:
        from isotope.features.supervisor import runner as api

    flow = CodexSupervisorFlow(codex_home=Path(args.codex_home))
    report = flow.scan(
        limit=args.limit,
        stale_after_seconds=args.stale_after,
        active_within_seconds=args.active_within,
    )
    fingerprint = report_fingerprint(report)
    if getattr(args, "changes_only", False) and previous_fingerprint == fingerprint:
        return False, fingerprint, previous_bell_fingerprint
    bell_fingerprint = attention_bell_fingerprint(report)
    if (
        getattr(args, "bell", False)
        and bell_fingerprint is not None
        and bell_fingerprint != previous_bell_fingerprint
    ):
        emit_terminal_bell()
    if args.json:
        payload = report.to_dict()
        if args.llm_summary:
            payload["llm_summary"] = summarize_with_llm(report)
        api._print_json(payload)
    else:
        print(render_plain_report(report))
        if args.llm_summary:
            print()
            print("[LLM 摘要]")
            print(summarize_with_llm(report))
    return True, fingerprint, bell_fingerprint


def scan_report(args: argparse.Namespace, *, api: Any | None = None) -> Any:
    if api is None:
        from isotope.features.supervisor import runner as api

    api._sync_managed_worker_failures(
        codex_home=Path(args.codex_home),
        max_run_minutes=getattr(args, "max_run_minutes", DEFAULT_MAX_RUN_MINUTES),
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
        else unknown_tmux_bell_hook,
        tmux_pane_reader=api._tmux_capture_pane if needs_tmux_pane else None,
    )
    return flow.scan(
        limit=args.limit,
        stale_after_seconds=args.stale_after,
        active_within_seconds=args.active_within,
    )


def unknown_tmux_bell_hook(_session: str) -> None:
    return None


def emit_terminal_bell() -> None:
    sys.stderr.write("\a")
    sys.stderr.flush()


def summarize_with_llm(report: Any) -> str:
    from isotope.features.supervisor import runner as api

    provider = api.resolve_summary_provider_from_env(agent_name="supervisor")
    return generate_llm_summary(report, provider)
