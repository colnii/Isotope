"""Memory-related parser registration for the Supervisor CLI."""

from __future__ import annotations

import argparse


def add_memory_command_parsers(subparsers: argparse._SubParsersAction) -> None:
    memory_parser = subparsers.add_parser(
        "memory",
        help="Show a public summary of local memory records.",
    )
    memory_parser.add_argument(
        "--root",
        default=".",
        help="Runtime root containing memory/*.json. Defaults to current directory.",
    )
    memory_parser.add_argument(
        "--scope",
        choices=("thread", "run", "session"),
        help="Only show one memory scope.",
    )
    memory_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum records to preview.",
    )
    memory_parser.add_argument(
        "--query",
        help="Search public memory summaries and references.",
    )
    memory_parser.add_argument(
        "--run-id",
        help="Only include records with matching provenance.run_id.",
    )
    memory_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    worker_event_parser = subparsers.add_parser(
        "worker-event",
        help="Publish or list memory-backed worker events.",
    )
    worker_event_subparsers = worker_event_parser.add_subparsers(
        dest="worker_event_command",
        required=True,
    )
    worker_event_publish = worker_event_subparsers.add_parser(
        "publish",
        help="Publish one worker event into the memory-backed channel.",
    )
    worker_event_publish.add_argument(
        "--root",
        default=".",
        help="Runtime root containing memory/*.json. Defaults to current directory.",
    )
    worker_event_publish.add_argument("--from", dest="from_worker", required=True)
    worker_event_publish.add_argument("--to", dest="to_worker")
    worker_event_publish.add_argument("--type", dest="event_type", default="message")
    worker_event_publish.add_argument("--channel", default="default")
    worker_event_publish.add_argument("--message", required=True)
    worker_event_publish.add_argument(
        "--payload-json",
        help="Optional JSON object payload for the event.",
    )
    worker_event_publish.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output.",
    )
    worker_event_list = worker_event_subparsers.add_parser(
        "list",
        help="List worker events from the memory-backed channel.",
    )
    worker_event_list.add_argument(
        "--root",
        default=".",
        help="Runtime root containing memory/*.json. Defaults to current directory.",
    )
    worker_event_list.add_argument("--from", dest="from_worker")
    worker_event_list.add_argument("--to", dest="to_worker")
    worker_event_list.add_argument("--type", dest="event_type")
    worker_event_list.add_argument("--channel")
    worker_event_list.add_argument("--limit", type=int, default=20)
    worker_event_list.add_argument("--json", action="store_true", help="Print JSON output.")
    worker_manager_parser = subparsers.add_parser(
        "worker-manager",
        help="Show a memory-backed multi-worker status view.",
    )
    worker_manager_parser.add_argument(
        "--root",
        default=".",
        help="Runtime root containing memory/*.json. Defaults to current directory.",
    )
    worker_manager_parser.add_argument("--worker", help="Only show one worker.")
    worker_manager_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum workers to preview.",
    )
    worker_manager_parser.add_argument("--json", action="store_true", help="Print JSON output.")
