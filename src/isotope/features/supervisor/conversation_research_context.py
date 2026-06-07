"""Low-sensitive research context projection for chained chat capabilities."""

from __future__ import annotations

import json
from typing import Any

MAX_RESEARCH_CONTEXT_CHARS = 6000
MAX_RESEARCH_CONTEXT_ITEMS = 3
MAX_RESEARCH_SOURCE_PREVIEWS = 5


def research_context_from_observations(
    observations: list[dict[str, Any]] | None,
) -> str | None:
    if not observations:
        return None
    items = [
        item
        for observation in observations
        if (item := _research_context_item(observation)) is not None
    ]
    if not items:
        return None
    payload = {
        "kind": "conversation_research_context",
        "items": items[-MAX_RESEARCH_CONTEXT_ITEMS:],
    }
    return _clip_context(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _research_context_item(observation: dict[str, Any]) -> dict[str, Any] | None:
    if observation.get("capacity_id") != "research.search":
        return None
    result = observation.get("result")
    if not isinstance(result, dict):
        return None
    item: dict[str, Any] = {
        key: value
        for key, value in {
            "status": _string_value(result.get("agent_loop_research_search_status")),
            "report": _string_value(result.get("agent_loop_research_report")),
            "source_count": _int_value(result.get("agent_loop_research_source_count")),
        }.items()
        if value not in ("", 0, None)
    }
    sources = _safe_source_previews(
        result.get("agent_loop_research_source_previews")
    )
    if sources:
        item["sources"] = sources
    return item or None


def _safe_source_previews(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    previews: list[dict[str, str]] = []
    for raw in value[:MAX_RESEARCH_SOURCE_PREVIEWS]:
        if not isinstance(raw, dict):
            continue
        preview = {
            key: text
            for key in ("source_id", "title", "url", "snippet")
            if (text := _string_value(raw.get(key))) != ""
        }
        if preview:
            previews.append(preview)
    return previews


def _string_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _int_value(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _clip_context(text: str) -> str:
    if len(text) <= MAX_RESEARCH_CONTEXT_CHARS:
        return text
    return text[:MAX_RESEARCH_CONTEXT_CHARS] + "\n...[truncated]"
