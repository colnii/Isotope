"""Goal scope helpers for Supervisor planning."""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import Any


def _selected_active_goal(args: argparse.Namespace) -> dict[str, Any] | None:
    runner = importlib.import_module("isotope.features.supervisor.runner")
    return runner._selected_active_goal(args)


def _goal_text(args: argparse.Namespace) -> str | None:
    explicit = _explicit_goal_text(args)
    if explicit is not None:
        return explicit
    active_goal = _selected_active_goal(args)
    return active_goal.get("goal") if active_goal else None


def _explicit_goal_text(args: argparse.Namespace) -> str | None:
    raw = getattr(args, "goal", None)
    if not isinstance(raw, str):
        return None
    return raw.strip() or None


def _goal_workspace(args: argparse.Namespace) -> str | None:
    raw = getattr(args, "goal", None)
    if isinstance(raw, str) and raw.strip():
        workspace = _explicit_goal_workspace(args)
        return str(workspace.resolve())
    active_goal = _selected_active_goal(args)
    if active_goal and isinstance(active_goal.get("cwd"), str):
        return active_goal["cwd"]
    return None


def _goal_target_name(args: argparse.Namespace) -> str | None:
    raw = getattr(args, "goal", None)
    if isinstance(raw, str) and raw.strip():
        return None
    active_goal = _selected_active_goal(args)
    if active_goal and isinstance(active_goal.get("target_name"), str):
        return active_goal["target_name"]
    return None


def _explicit_goal_workspace(args: argparse.Namespace) -> Path:
    raw = getattr(args, "workspace_root", None)
    return Path(raw).expanduser() if isinstance(raw, str) and raw else Path.cwd()
