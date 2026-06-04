"""Public capability gap projections for Supervisor surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CLOSED_GAP_STATUSES = {"resolved", "closed", "archived"}


def read_open_capability_gaps(
    *, state_root: Path | str, limit: int = 10
) -> list[dict[str, Any]]:
    gaps = [
        gap
        for gap in _read_capability_gap_summaries(state_root)
        if gap.get("status") not in CLOSED_GAP_STATUSES
    ]
    gaps.sort(key=lambda gap: str(gap.get("created_at") or ""), reverse=True)
    return gaps[:limit]


def read_capability_gap(
    *, state_root: Path | str, gap_id: str
) -> dict[str, Any] | None:
    gap_id_text = gap_id.strip()
    if not gap_id_text:
        return None
    for gap in _read_capability_gap_summaries(state_root):
        if gap.get("gap_id") == gap_id_text:
            return gap
    return None


def _read_capability_gap_summaries(state_root: Path | str) -> list[dict[str, Any]]:
    gap_dir = Path(state_root).expanduser() / "supervisor" / "capability-gaps"
    if not gap_dir.is_dir():
        return []
    gaps: list[dict[str, Any]] = []
    for path in sorted(gap_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        summary = _capability_gap_summary(raw)
        if summary is not None:
            gaps.append(summary)
    return gaps


def _capability_gap_summary(raw: dict[str, Any]) -> dict[str, Any] | None:
    gap_id = _string(raw.get("gap_id"))
    if not gap_id:
        return None
    return {
        "kind": _string(raw.get("kind")) or "capability_gap",
        "gap_id": gap_id,
        "status": _string(raw.get("status")) or "recorded",
        "missing_capability_kind": (
            _string(raw.get("missing_capability_kind")) or "unknown"
        ),
        "reason": _string(raw.get("reason")) or "capability gap reported",
        "needed_context": _string_list(raw.get("needed_context")),
        "suggested_next_capability": _string(raw.get("suggested_next_capability")) or "",
        "source_entrypoint": _string(raw.get("source_entrypoint")) or "",
        "created_at": _string(raw.get("created_at")) or "",
    }


def _string(value: Any) -> str:
    return value.strip()[:1000] if isinstance(value, str) and value.strip() else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item.strip()[:500]
        for item in value[:20]
        if isinstance(item, str) and item.strip()
    ]


__all__ = [
    "read_capability_gap",
    "read_open_capability_gaps",
]
