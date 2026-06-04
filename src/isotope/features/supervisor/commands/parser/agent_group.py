"""Agent group parser registration for the Supervisor CLI."""

from __future__ import annotations

import argparse

from .common import add_state_root_arg


def add_agent_group_command_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "agent-group",
        help="Create and tick internal Supervisor Agent groups.",
    )
    group_subparsers = parser.add_subparsers(
        dest="agent_group_command",
        required=True,
    )

    create = group_subparsers.add_parser("create", help="Create an Agent group.")
    add_state_root_arg(create)
    create.add_argument("--title", default="Agent group")
    create.add_argument("--goal", required=True)
    create.add_argument(
        "--member",
        action="append",
        default=[],
        help="Member spec as name:role:goal. Repeatable.",
    )
    create.add_argument("--message", required=True)
    create.add_argument("--json", action="store_true", help="Print JSON output.")

    send = group_subparsers.add_parser("send", help="Send a message into a group.")
    add_state_root_arg(send)
    send.add_argument("--group", required=True, dest="group_id")
    send.add_argument("--message", required=True)
    send.add_argument("--from", dest="from_member", default="supervisor")
    send.add_argument("--to", dest="to_member")
    send.add_argument("--type", dest="message_type", default="task")
    send.add_argument("--json", action="store_true", help="Print JSON output.")

    tick = group_subparsers.add_parser("tick", help="Run one Agent group turn.")
    add_state_root_arg(tick)
    tick.add_argument("--group", required=True, dest="group_id")
    tick.add_argument("--max-visible-messages", type=int, default=2)
    tick.add_argument("--json", action="store_true", help="Print JSON output.")

    list_parser = group_subparsers.add_parser("list", help="List Agent groups.")
    add_state_root_arg(list_parser)
    list_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    inspect = group_subparsers.add_parser("inspect", help="Inspect one Agent group.")
    add_state_root_arg(inspect)
    inspect.add_argument("--group", required=True, dest="group_id")
    inspect.add_argument("--json", action="store_true", help="Print JSON output.")
