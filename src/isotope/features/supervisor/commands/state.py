"""Supervisor state projection command helpers."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from isotope.features.supervisor.state.projection import (
    build_supervisor_state_snapshot,
)


def handle_state_command(args: argparse.Namespace, *, api: Any) -> int:
    payload = state_payload(args)
    if args.json:
        api._print_json(payload)
    else:
        print_state_plain(payload)
    return 0


def state_payload(args: argparse.Namespace) -> dict[str, Any]:
    return build_supervisor_state_snapshot(codex_home=Path(args.codex_home))


def print_state_plain(payload: dict[str, Any]) -> None:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    print("[Supervisor state]")
    print(f"codex_home：{payload.get('codex_home', '')}")
    print(f"active goals：{summary.get('active_goals', 0)}")
    print(f"decisions：{summary.get('active_decisions', 0)}")
    print(f"failed lanes：{summary.get('failed_lanes', 0)}")
    print(f"worker events：{summary.get('worker_events', 0)}")
    print(
        "notifications："
        f"{summary.get('notifications', 0)} / unread "
        f"{summary.get('unread_notifications', 0)}"
    )
