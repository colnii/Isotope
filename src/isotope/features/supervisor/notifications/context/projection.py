"""Low-sensitive projections for Supervisor project context results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def request_context_model_observation(
    capability_run: Mapping[str, Any],
) -> dict[str, Any] | None:
    context_result = _context_result(capability_run)
    if context_result is None:
        return None
    safe_items = _safe_context_items(context_result)
    return _omit_empty(
        {
            "kind": "request_context",
            "status": _string_value(capability_run.get("status")),
            "query": _string_value(context_result.get("query")),
            "backend": _string_value(context_result.get("backend")),
            "item_count": _item_count(context_result, safe_items),
            "items": safe_items,
        }
    )


def request_context_agent_loop_result(
    capability_run: Mapping[str, Any],
) -> dict[str, Any]:
    if capability_run.get("capability_id") != "supervisor.request_context":
        return {}
    context_result = _context_result(capability_run)
    if context_result is None:
        return {}
    safe_items = _safe_context_items(context_result)
    result = {
        "agent_loop_request_context_status": capability_run.get("status"),
        "agent_loop_request_context_query": context_result.get("query"),
        "agent_loop_request_context_backend": context_result.get("backend"),
        "agent_loop_request_context_item_count": _item_count(context_result, safe_items),
    }
    if safe_items:
        result["agent_loop_request_context_items"] = safe_items
    return result


def _context_result(capability_run: Mapping[str, Any]) -> Mapping[str, Any] | None:
    context_result = capability_run.get("context_result")
    return context_result if isinstance(context_result, Mapping) else None


def _safe_context_items(context_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_items = context_result.get("items")
    if not isinstance(raw_items, list):
        return []
    safe_items = [
        _safe_context_item(item)
        for item in raw_items[:5]
        if isinstance(item, Mapping)
    ]
    return [item for item in safe_items if item is not None]


def _safe_context_item(item: Mapping[str, Any]) -> dict[str, Any] | None:
    path = item.get("path")
    line = item.get("line")
    snippet = item.get("snippet")
    if not isinstance(path, str) or not isinstance(line, int):
        return None
    if not isinstance(snippet, str) or not snippet.strip():
        return None
    return _omit_empty(
        {
            "path": path,
            "line": line,
            "title": _string_value(item.get("title")),
            "snippet": _clip(snippet.strip(), limit=700),
            "match_reason": _string_value(item.get("match_reason")),
            "source_group": _string_value(item.get("source_group")),
        }
    )


def _item_count(
    context_result: Mapping[str, Any],
    safe_items: list[dict[str, Any]],
) -> int:
    item_count = context_result.get("item_count")
    if isinstance(item_count, int) and not isinstance(item_count, bool):
        return item_count
    raw_items = context_result.get("items")
    return len(raw_items) if isinstance(raw_items, list) else len(safe_items)


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _clip(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _omit_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item not in (None, "", [], {})
    }
