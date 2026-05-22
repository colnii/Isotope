"""Dashboard command handling for the Supervisor CLI."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from isotope.features.supervisor.state.multi_worker import (
    build_multi_worker_status_payload,
)


def handle_dashboard_command(args: argparse.Namespace, *, api: Any) -> int:
    report = api._scan_report(args)
    payload = api._dashboard_payload(
        report,
        active_goals=api._active_goal_dicts(args, include_status=True),
        decision_requests=api._decision_request_dicts(args),
        notifications=api._notification_dicts(Path(args.codex_home)),
        multi_worker=build_multi_worker_status_payload(root=Path(args.codex_home)),
    )
    if args.json:
        api._print_json(payload)
    else:
        api._print_dashboard_plain(payload)
    return 0
