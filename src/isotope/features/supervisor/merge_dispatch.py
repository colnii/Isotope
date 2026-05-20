"""Build controlled merge-dispatch launch specs from integration reviews."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .merge_work_order import build_merge_work_order_prompt

DEFAULT_TARGET_NAME = "supervisor-merge-dispatch"
REVIEW_NOTE = "merge dispatch only builds a controlled launch spec; runner launch gates still apply."


def build_merge_dispatch_launch_spec(
    payload: Mapping[str, Any],
    *,
    cwd: str,
    target_name: str = DEFAULT_TARGET_NAME,
    requires_human_review: bool = True,
) -> dict[str, Any] | None:
    """Convert an integration-review payload into one merge worker launch spec."""
    launch_cwd = _required_text(cwd, field_name="cwd")
    launch_target = _required_text(target_name, field_name="target_name")
    ready_workers = _ready_workers(payload)
    if not ready_workers:
        return None

    return {
        "kind": "launch_session",
        "target_name": launch_target,
        "worker_role": "merge_dispatch",
        "cwd": launch_cwd,
        "prompt": build_merge_work_order_prompt(payload),
        "reason": "ready_to_integrate workers require merge dispatch",
        "source": "integration_review",
        "integration_summary": {
            "base_ref": _base_ref(payload),
            "ready_to_integrate": len(ready_workers),
        },
        "review": {
            "requires_human_review": requires_human_review,
            "note": REVIEW_NOTE,
        },
    }


def _ready_workers(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    groups = payload.get("groups")
    if not isinstance(groups, Mapping):
        return []
    raw_ready = groups.get("ready_to_integrate")
    if not isinstance(raw_ready, list):
        return []
    return [item for item in raw_ready if isinstance(item, Mapping)]


def _base_ref(payload: Mapping[str, Any]) -> str:
    value = payload.get("base_ref")
    text = str(value).strip() if value is not None else ""
    return text or "main"


def _required_text(value: object, *, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


__all__ = [
    "DEFAULT_TARGET_NAME",
    "REVIEW_NOTE",
    "build_merge_dispatch_launch_spec",
]
