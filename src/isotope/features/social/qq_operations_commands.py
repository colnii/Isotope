"""Operational command handlers for QQ social commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .lorebook import Lorebook
from .operations import SocialOperationsController
from .qq_state_config import (
    character_card_from_config,
    load_config,
    load_state,
    optional_lorebook_from_config,
    optional_stickers_from_config,
    operations_from_config,
    save_state,
    state_path,
    write_json_file,
)
from .stickers import StickerLibrary


def handle_pause_resume(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(Path(args.config_json))
    state_root = Path(args.state_root)
    operations = operations_from_config(config, state=load_state(state_root))
    if args.command == "pause":
        result = operations.pause_group(args.group, operator_user_id=args.operator)
    else:
        result = operations.resume_group(args.group, operator_user_id=args.operator)
    save_state(state_root, operations)
    return {
        "status": "ok" if result.get("ok") else "blocked",
        "command": args.command,
        "result": result,
        "state_file": str(state_path(state_root)),
    }


def handle_inspect(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(Path(args.config_json))
    operations = SocialOperationsController()
    if args.target == "role":
        return {"status": "ok", "role": operations.inspect_role(character_card_from_config(config))}
    if args.target == "lorebook":
        lorebook = optional_lorebook_from_config(config) or Lorebook()
        return {"status": "ok", "lorebook": operations.inspect_lorebook(lorebook)}
    if args.target == "stickers":
        stickers = optional_stickers_from_config(config) or StickerLibrary(entries=())
        return {"status": "ok", "stickers": operations.inspect_stickers(stickers)}
    raise ValueError(f"unknown inspect target: {args.target}")


def handle_health(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(Path(args.config_json))
    operations = operations_from_config(config, state=load_state(Path(args.state_root)))
    return {"status": "ok", "health": operations.health_check()}


def handle_export_log(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(Path(args.state_root))
    output = Path(args.output)
    entries = [
        entry
        for entry in state.audit_entries
        if entry.get("group_id") == str(args.group)
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json_file(output, {"entries": entries})
    return {
        "status": "ok",
        "group_id": str(args.group),
        "output": str(output),
        "entry_count": len(entries),
    }
