"""Memory and worker event command handlers for the Supervisor CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from isotope.features.supervisor.state.memory_view import (
    build_memory_query_payload,
    build_memory_status_payload,
    render_memory_query_plain,
    render_memory_status_plain,
)
from isotope.platform.state.multi_worker import (
    build_multi_worker_status_payload,
    render_multi_worker_status_plain,
)
from isotope.platform.state.worker_event_channel import (
    list_worker_events,
    publish_worker_event,
    render_worker_event_channel_plain,
)


def handle_memory_command(args: argparse.Namespace, *, api: Any) -> int:
    if args.query:
        payload = build_memory_query_payload(
            root=Path(args.root),
            query=args.query,
            scope=args.scope,
            run_id=args.run_id,
            limit=args.limit,
        )
        plain = render_memory_query_plain(payload)
    else:
        payload = build_memory_status_payload(
            root=Path(args.root),
            scope=args.scope,
            limit=args.limit,
        )
        plain = render_memory_status_plain(payload)
    if args.json:
        api._print_json(payload)
    else:
        print(plain)
    return 0


def handle_worker_event_command(args: argparse.Namespace, *, api: Any) -> int:
    if args.worker_event_command == "publish":
        payload = publish_worker_event(
            root=Path(args.root),
            from_worker=args.from_worker,
            to_worker=args.to_worker,
            event_type=args.event_type,
            channel=args.channel,
            message=args.message,
            payload=json_object_arg(args.payload_json, "payload-json"),
        )
        if args.json:
            api._print_json(payload)
        else:
            print(
                render_worker_event_channel_plain(
                    {"store": payload["store"], "events": [payload["event"]]}
                )
            )
        return 0
    if args.worker_event_command == "list":
        payload = list_worker_events(
            root=Path(args.root),
            channel=args.channel,
            from_worker=args.from_worker,
            to_worker=args.to_worker,
            event_type=args.event_type,
            limit=args.limit,
        )
        if args.json:
            api._print_json(payload)
        else:
            print(render_worker_event_channel_plain(payload))
        return 0
    raise ValueError(f"unsupported worker-event command: {args.worker_event_command}")


def handle_worker_manager_command(args: argparse.Namespace, *, api: Any) -> int:
    payload = build_multi_worker_status_payload(
        root=Path(args.root),
        worker=args.worker,
        limit=args.limit,
    )
    if args.json:
        api._print_json(payload)
    else:
        print(render_multi_worker_status_plain(payload))
    return 0


def json_object_arg(raw: str | None, field_name: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be a JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return value
