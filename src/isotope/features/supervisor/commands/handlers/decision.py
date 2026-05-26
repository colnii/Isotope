"""Decision request command helpers for the Supervisor CLI."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Any


def handle_decision_command(args: argparse.Namespace, *, api: Any) -> int:
    payload = decision_payload(args, api=api)
    if args.json:
        api._print_json(payload)
    else:
        print_decision_plain(payload)
    return 0


def decision_payload(
    args: argparse.Namespace,
    *,
    api: Any,
) -> dict[str, Any]:
    if args.decision_command == "list":
        return {
            "status": "ok",
            "decision_requests": api._decision_request_dicts(args),
        }
    if args.decision_command == "archive":
        archived = api.archive_decision_request(
            codex_home=Path(args.codex_home),
            request_id=args.request_id,
        )
        return {
            "status": "ok",
            "archived": archived,
            "decision_requests": api._decision_request_dicts(args),
        }
    if args.decision_command == "answer":
        answered = api.record_decision_answer(
            codex_home=Path(args.codex_home),
            request_id=args.request_id,
            answer=args.answer,
            webhook_url=args.webhook_url,
            webhook_secret=args.webhook_secret,
        )
        return {
            "status": "ok",
            "answered": answered,
            "decision_requests": api._decision_request_dicts(args),
            "recent_decision_answers": api._decision_answer_dicts(args),
        }
    raise ValueError(f"unsupported decision command: {args.decision_command}")


def print_decision_plain(payload: dict[str, Any]) -> None:
    archived = payload.get("archived")
    if isinstance(archived, dict):
        print(f"已归档拍板请求：{archived['request_id']}")
    answered = payload.get("answered")
    if isinstance(answered, dict):
        print(f"已记录拍板答案：{answered['request_id']}")
    requests = payload.get("decision_requests") or []
    print(f"等待拍板：{len(requests)}")
    for item in requests:
        archive_command = shlex.join(
            [
                "isotope-supervisor",
                "decision",
                "archive",
                "--request-id",
                item["request_id"],
            ]
        )
        target = item.get("target_name") or item.get("session_id") or "未知"
        context_status = item.get("context_status") or "unknown"
        print(f"- {item['request_id']} {item['question']}")
        print(f"  target={target} context={context_status}")
        print(f"  归档：{archive_command}")
