"""Reusable append-only failure ledger for retry guardrails."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class FailureLedger:
    """Append-only JSONL ledger for low-sensitive failure events."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser()

    def record_failure(
        self,
        *,
        event_type: str,
        lane_name: str | None,
        goal_id: str | None,
        error_summary: str,
        now: Callable[[], datetime] | None = None,
    ) -> dict[str, Any]:
        event_type_text = _required_string(event_type, "event_type")
        error_summary_text = _required_string(error_summary, "error_summary")
        lane_name_text = _optional_string(lane_name)
        goal_id_text = _optional_string(goal_id)
        retry_count = self._previous_retry_count(
            event_type=event_type_text,
            lane_name=lane_name_text,
            goal_id=goal_id_text,
        ) + 1
        event = {
            "timestamp": _ensure_aware_utc((now or _utc_now)()).isoformat(),
            "event_type": event_type_text,
            "lane_name": lane_name_text,
            "goal_id": goal_id_text,
            "error_summary": _clip(error_summary_text),
            "retry_count": retry_count,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
        return event

    def read_recent(self, *, limit: int = 20) -> tuple[dict[str, Any], ...]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if not self.path.is_file():
            return ()
        events: list[dict[str, Any]] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ()
        for line in lines:
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                events.append(raw)
        return tuple(reversed(events[-limit:]))

    def _previous_retry_count(
        self,
        *,
        event_type: str,
        lane_name: str | None,
        goal_id: str | None,
    ) -> int:
        for event in self.read_recent(limit=1000):
            if (
                event.get("event_type") == event_type
                and event.get("lane_name") == lane_name
                and event.get("goal_id") == goal_id
            ):
                retry_count = event.get("retry_count")
                return retry_count if isinstance(retry_count, int) else 1
        return 0


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _clip(value: str, *, limit: int = 300) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
