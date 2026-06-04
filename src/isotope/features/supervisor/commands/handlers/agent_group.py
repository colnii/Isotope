"""Agent group command handlers."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from isotope.features.supervisor.agent_group.runtime import AgentGroupRuntime


def handle_agent_group_command(args: argparse.Namespace, *, api: Any) -> int:
    runtime = AgentGroupRuntime(Path(args.codex_home))
    if args.agent_group_command == "create":
        payload = runtime.create_group(
            title=args.title,
            goal=args.goal,
            member_specs=[_member_spec(raw) for raw in args.member],
            initial_message=args.message,
        )
        return _print(payload, json_output=args.json, api=api)
    if args.agent_group_command == "send":
        payload = runtime.send_message(
            group_id=args.group_id,
            message=args.message,
            from_member=args.from_member,
            to_member=args.to_member,
            message_type=args.message_type,
        )
        return _print(payload, json_output=args.json, api=api)
    if args.agent_group_command == "tick":
        payload = runtime.tick_group(
            args.group_id,
            max_visible_messages=args.max_visible_messages,
        )
        return _print(payload, json_output=args.json, api=api)
    if args.agent_group_command == "list":
        payload = runtime.list_groups()
        return _print(payload, json_output=args.json, api=api)
    if args.agent_group_command == "inspect":
        payload = runtime.list_group(args.group_id)
        return _print(payload, json_output=args.json, api=api)
    raise ValueError(f"unsupported agent-group command: {args.agent_group_command}")


def _member_spec(raw: str) -> dict[str, str]:
    parts = raw.split(":", 2)
    if len(parts) != 3 or not all(part.strip() for part in parts):
        raise ValueError("member must use name:role:goal")
    return {
        "name": parts[0].strip(),
        "role": parts[1].strip(),
        "goal": parts[2].strip(),
    }


def _print(payload: dict[str, Any], *, json_output: bool, api: Any) -> int:
    if json_output:
        api._print_json(payload)
    else:
        print_agent_group_plain(payload)
    return 0


def print_agent_group_plain(payload: dict[str, Any]) -> None:
    group = payload.get("group") if isinstance(payload.get("group"), dict) else None
    if group is not None:
        print("[Agent group]")
        print(f"group: {group.get('group_id', '')}")
        print(f"title: {group.get('title', '')}")
        print(f"goal: {group.get('goal', '')}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else None
    if summary is not None:
        print("[Agent groups]")
        print(f"groups: {summary.get('group_count', 0)}")
    members = payload.get("members")
    if isinstance(members, list):
        print("members:")
        for member in members:
            if isinstance(member, dict):
                print(f"- {member.get('name', '')}: {member.get('role', '')}")
    messages = payload.get("messages")
    if isinstance(messages, list):
        print("messages:")
        for message in messages[-10:]:
            if isinstance(message, dict):
                print(
                    "- {from_member} -> {to_member}: {summary}".format(
                        from_member=message.get("from_member", ""),
                        to_member=message.get("to_member") or "*",
                        summary=message.get("summary", ""),
                    )
                )
    turn = payload.get("turn") if isinstance(payload.get("turn"), dict) else None
    if turn is not None:
        print("[Agent group turn]")
        print(f"status: {turn.get('status', '')}")
        print(f"summary: {turn.get('supervisor_summary', '')}")
