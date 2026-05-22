"""Merge and integration-review command handling for the Supervisor CLI."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from isotope.features.supervisor.integration_review import render_integration_review_plain
from isotope.features.supervisor.merge_work_order import build_merge_work_order_prompt


def handle_integration_review_command(args: argparse.Namespace, *, api: Any) -> int:
    payload = api.collect_integration_reviews(
        codex_home=Path(args.codex_home),
        base_ref=args.base,
        include_unfinished=args.include_unfinished,
        include_missing_worktrees=args.include_missing_worktrees,
    )
    api._notify_integration_review_webhooks(args, payload)
    if args.json:
        api._print_json(payload)
    else:
        print(render_integration_review_plain(payload))
    return 0


def handle_merge_work_order_command(args: argparse.Namespace, *, api: Any) -> int:
    review_payload = api.collect_integration_reviews(
        codex_home=Path(args.codex_home),
        base_ref=args.base,
        include_unfinished=False,
    )
    prompt = build_merge_work_order_prompt(review_payload)
    if args.json:
        api._print_json(
            {
                "status": review_payload.get("status", "ok"),
                "summary": review_payload.get("summary", {}),
                "prompt": prompt,
            }
        )
    else:
        print(prompt)
    return 0
