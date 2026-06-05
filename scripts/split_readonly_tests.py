#!/usr/bin/env python3
"""Split tests/integration/codex/test_codex_supervisor_readonly.py into domain files.

Usage:
    .venv/bin/python scripts/split_readonly_tests.py [--dry-run]

Output goes to tests/integration/codex/ as separate test_*.py files.
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

SRC = Path("tests/integration/codex/test_codex_supervisor_readonly.py")
OUT_DIR = Path("tests/integration/codex")

COMMON_IMPORTS = """\
from __future__ import annotations

import argparse
import http.client
import json
import os
import signal
import shlex
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from helpers import (
    CONTINUE_REQUEST_TEXT,
    EXISTING_WORKSPACE,
    NON_STALE_SECONDS,
    NOW,
    STATUS_REQUEST_TEXT,
    _add_supervisor_goal,
    _append_supervisor_goal_status,
    _assistant_message,
    _codex_operation_context_result,
    _event,
    _record_cleanup_lifecycle_execution,
    _runner_args,
    _supervisor_send_command,
    _tmux_send_calls,
    _user_message,
    _write_managed_tmux_record,
    _write_session,
    _write_session_index,
    _write_state_threads,
)
from isotope.features.notifications.flow import NotificationFlow
from isotope.features.supervisor import flow as supervisor_flow
from isotope.features.supervisor import runner as supervisor_runner
from isotope.features.supervisor.flow import (
    CodexSessionSummary,
    CodexSupervisorFlow,
    CodexSupervisorReport,
    render_plain_report,
)
from isotope.features.supervisor.llm_action.llm_summary import (
    PoolEntry,
    PooledSummaryProvider,
    build_llm_action_messages,
    build_llm_summary_messages,
    generate_llm_action_decision,
    generate_llm_summary,
    resolve_summary_provider_from_env,
)
from isotope.features.supervisor.merge.merge_dispatch import DEFAULT_TARGET_NAME
from isotope.features.supervisor.notifications.context import (
    read_recent_context_results,
    request_project_context,
)
from isotope.features.supervisor.runner import (
    EXECUTABLE_ADVICE_TEXT,
    _advice_payload,
    _dashboard_payload,
    _execute_context_action,
    _execute_llm_action,
    _print_dashboard_plain,
    _report_fingerprint,
    _supervise_payload,
    main as supervisor_main,
)
from isotope.features.supervisor.state.worker_lifecycle import (
    record_worker_lifecycle_decision,
)
"""


def read_source() -> list[str]:
    return SRC.read_text().splitlines(keepends=True)


def group_test(name: str) -> str:
    """Map a test function name to its target file name (without .py)."""
    domain = name.removeprefix("test_codex_supervisor_")

    groups: dict[str, str] = {
        # Additional mappings for non-standard prefixes
        "advise": "test_runner_advise",
        "execute_llm": "test_llm_action",
        "generate_llm_action": "test_llm_action",
        "generate_llm_summary": "test_pooled_provider",
        "llm_action": "test_llm_action",
        "llm_execute_blocks": "test_runner_supervise",
        "llm_messages": "test_pooled_provider",
        "overnight_plain": "test_dashboard",
        "parser_accepts": "test_llm_action",
        "pool_accepts": "test_pooled_provider",
        "send_continue": "test_runner_supervise",
        "send_status": "test_runner_supervise",
        "start_here": "test_other",
        "state_plain": "test_dashboard",
        "context_request": "test_other",
        "cleanup_list_skips": "test_runner_cleanup",
        # scan + report + recommendation
        "scan": "test_scan",
        "protocol_status": "test_scan",
        "report": "test_scan",
        "plain_report": "test_scan",
        "avoids_broad": "test_scan",
        "recommendation": "test_scan",
        "display_title": "test_scan",
        "first_user_title": "test_scan",
        # dashboard
        "dashboard": "test_dashboard",
        "fallback_snapshot": "test_dashboard",
        "snapshot_meta": "test_dashboard",
        "current_batch": "test_dashboard",
        "managed_terminal": "test_dashboard",
        "loop_payload": "test_dashboard",
        # web
        "web": "test_web",
        # runner_advise
        "runner_advise": "test_runner_advise",
        "runner_advice": "test_runner_advise",
        "runner_web": "test_runner_advise",
        # runner_scan
        "runner_scan": "test_runner_scan",
        "runner_dashboard": "test_runner_scan",
        "runner_check": "test_runner_scan",
        "runner_overnight": "test_runner_scan",
        # runner_cleanup
        "runner_cleanup": "test_runner_cleanup",
        "runner_decision": "test_runner_cleanup",
        "runner_decide": "test_runner_cleanup",
        "runner_goal": "test_runner_cleanup",
        "runner_archive": "test_runner_cleanup",
        # runner_loop
        "runner_loop": "test_runner_loop",
        # runner_supervise
        "runner_supervise": "test_runner_supervise",
        "runner_supervisor": "test_runner_supervise",
        "runner_execute": "test_runner_supervise",
        "runner_llm": "test_runner_supervise",
        "runner_watch": "test_runner_supervise",
        # runner_daemon
        "runner_daemon": "test_runner_daemon",
        "runner_up": "test_runner_daemon",
        "daemon": "test_runner_daemon",
        # runner_launch (includes discover, resume, adopt, repair, send, guide)
        "runner_launch": "test_runner_launch",
        "runner_resume": "test_runner_launch",
        "runner_adopt": "test_runner_launch",
        "runner_repair": "test_runner_launch",
        "runner_discover": "test_runner_launch",
        "runner_send": "test_runner_launch",
        "runner_guide": "test_runner_launch",
        # pooled_provider
        "pooled_provider": "test_pooled_provider",
        "env_resolver": "test_pooled_provider",
        "llm_messages": "test_pooled_provider",
        "generate_llm_summary": "test_pooled_provider",
        # other — fold into catch-all
    }

    for key in sorted(groups.keys(), key=len, reverse=True):
        if domain.startswith(key):
            return groups[key]
    return "test_other"


def parse_tests(lines: list[str]) -> list[tuple[int, int, str, str]]:
    """Return [(start_line, end_line, function_name, group_name), ...]."""
    test_defs: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        # Match any function definition — the name is everything after "def " before "("
        stripped = line.lstrip()
        if stripped.startswith("def "):
            # Extract name: everything between "def " and "("
            paren = line.find("(")
            if paren > 0:
                name = line[line.index("def ") + 4 : paren].strip()
                if name.startswith("test_codex_supervisor_"):
                    test_defs.append((i, name))

    entries: list[tuple[int, int, str, str]] = []
    for idx, (start, name) in enumerate(test_defs):
        end = test_defs[idx + 1][0] if idx + 1 < len(test_defs) else len(lines)
        group = group_test(name) if name.startswith("test_codex_supervisor_") else "test_other"
        entries.append((start, end, name, group))
    return entries


def write_file(filename: str, entries: list[tuple[int, int, str, str]], lines: list[str], dry_run: bool):
    if not entries:
        return

    path = OUT_DIR / filename
    body_lines: list[str] = []

    # Write imports
    body_lines.append(COMMON_IMPORTS)
    body_lines.append("\n")

    # Write each function body
    for start, end, name, _ in entries:
        for li in range(start, end):
            body_lines.append(lines[li])
        body_lines.append("\n")

    content = "".join(body_lines)

    if dry_run:
        print(f"  [dry-run] {filename}: {len(entries)} tests, ~{len(body_lines)} lines")
        return

    path.write_text(content)
    print(f"  wrote {filename}: {len(entries)} tests, {len(body_lines)} lines")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lines = read_source()
    entries = parse_tests(lines)

    # Group by target file
    file_map: dict[str, list[tuple[int, int, str, str]]] = defaultdict(list)
    for e in entries:
        file_map[e[3]].append(e)

    for filename in sorted(file_map.keys()):
        write_file(f"{filename}.py", file_map[filename], lines, args.dry_run)

    total = sum(len(v) for v in file_map.values())
    print(f"\nTotal: {total} tests across {len(file_map)} files")
    if not args.dry_run:
        print(f"\nTo check: pytest tests/integration/codex/ -q")


if __name__ == "__main__":
    main()
