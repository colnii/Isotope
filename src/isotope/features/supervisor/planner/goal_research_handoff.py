"""Attach completed research context to worker-facing goal text."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, TypeVar

MAX_HANDOFF_CHARS = 1800
MAX_REPORT_CHARS = 420
MAX_SOURCE_CHARS = 260
MAX_SOURCES = 4

CandidateT = TypeVar("CandidateT")


def attach_research_handoff_to_candidates(
    candidates: list[CandidateT],
    *,
    research_context: str | None,
) -> list[CandidateT]:
    handoff = research_handoff_text(research_context)
    if not handoff:
        return candidates
    return [
        candidate
        if _has_handoff(str(getattr(candidate, "goal", "")))
        else replace(candidate, goal=f"{getattr(candidate, 'goal')}\n\n{handoff}")
        for candidate in candidates
    ]


def research_handoff_text(research_context: str | None) -> str | None:
    if not isinstance(research_context, str) or not research_context.strip():
        return None
    reports, sources = _research_context_parts(research_context)
    if not reports and not sources:
        return _handoff_block([_clip(research_context, MAX_REPORT_CHARS)])
    lines: list[str] = []
    if reports:
        lines.append("Findings:")
        lines.extend(f"- {_clip(report, MAX_REPORT_CHARS)}" for report in reports[:2])
    if sources:
        lines.append("Sources:")
        lines.extend(_source_line(source) for source in sources[:MAX_SOURCES])
    return _handoff_block(lines)


def _research_context_parts(
    research_context: str,
) -> tuple[list[str], list[dict[str, str]]]:
    try:
        payload = json.loads(research_context)
    except json.JSONDecodeError:
        return ([research_context.strip()], [])
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return ([research_context.strip()], [])
    reports: list[str] = []
    sources: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        report = _string_value(item.get("report"))
        if report:
            reports.append(report)
        for source in _dict_list(item.get("sources")):
            safe = {
                key: value
                for key in ("source_id", "title", "url", "snippet")
                if (value := _string_value(source.get(key)))
            }
            if safe:
                sources.append(safe)
    return reports, sources


def _handoff_block(lines: list[str]) -> str:
    body = "\n".join(line for line in lines if line.strip())
    return _clip(f"Research handoff for worker:\n{body}", MAX_HANDOFF_CHARS)


def _source_line(source: dict[str, str]) -> str:
    prefix = f"- {source.get('source_id')}: " if source.get("source_id") else "- "
    title = source.get("title") or "untitled source"
    url = f" ({source['url']})" if source.get("url") else ""
    snippet = f" - {source['snippet']}" if source.get("snippet") else ""
    return _clip(f"{prefix}{title}{url}{snippet}", MAX_SOURCE_CHARS)


def _has_handoff(goal: str) -> bool:
    return "Research handoff for worker:" in goal


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _clip(text: str, limit: int) -> str:
    clean = "\n".join(
        " ".join(line.split()) for line in text.splitlines() if line.strip()
    )
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + "..."
