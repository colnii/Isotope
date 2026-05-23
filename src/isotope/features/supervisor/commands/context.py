"""Project context command handling for the Supervisor CLI."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def handle_context_command(args: argparse.Namespace, *, api: Any) -> int:
    result = api.request_project_context(
        codex_home=Path(args.codex_home),
        cwd=Path(args.cwd),
        query=args.query,
        max_results=args.limit,
    )
    if args.json:
        api._print_json({"status": "ok", "context": result.to_dict()})
    else:
        print(f"上下文：{result.query}")
        for item in result.items:
            print(f"{item.path}:{item.line}: {item.text}")
    return 0
