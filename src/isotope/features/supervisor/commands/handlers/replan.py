"""Replan command helpers for the Supervisor CLI."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from isotope.features.supervisor.replan import (
    build_supervisor_replan,
    render_supervisor_replan_plain,
)


def handle_replan_command(args: argparse.Namespace, *, api: Any) -> int:
    payload = replan_payload(args, api=api)
    if args.json:
        api._print_json(payload)
    else:
        print(render_supervisor_replan_plain(payload))
    return 0


def replan_payload(args: argparse.Namespace, *, api: Any) -> dict[str, Any]:
    return build_supervisor_replan(
        worker_reviews=api.collect_worker_reviews(codex_home=Path(args.codex_home)),
        integration_reviews=api.collect_integration_reviews(
            codex_home=Path(args.codex_home),
            base_ref=args.base,
            include_unfinished=args.include_unfinished,
        ),
        active_goals=api._active_goal_dicts(args, include_status=True),
    )
