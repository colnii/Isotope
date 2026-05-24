"""Web command runner for the Supervisor CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

def run_web(args: argparse.Namespace) -> None:
    if args.limit <= 0:
        raise ValueError("limit must be positive")
    if args.stale_after <= 0:
        raise ValueError("stale_after must be positive")
    if args.active_within <= 0:
        raise ValueError("active_within must be positive")
    if args.port < 0:
        raise ValueError("port must be zero or positive")
    url = f"http://{args.host}:{args.port}/"
    if args.print_url:
        print(url)
        return
    from .web import create_dashboard_server

    server = create_dashboard_server(
        codex_home=Path(args.codex_home),
        host=args.host,
        port=args.port,
        limit=args.limit,
        stale_after_seconds=args.stale_after,
        active_within_seconds=args.active_within,
    )
    actual_host, actual_port = server.server_address
    print(f"Codex Supervisor web: http://{actual_host}:{actual_port}/")
    try:
        server.serve_forever()
    finally:
        server.server_close()

__all__ = ("run_web",)
