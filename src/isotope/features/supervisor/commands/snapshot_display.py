"""Plain-display helpers for Supervisor state snapshots."""

from __future__ import annotations

from typing import Any


STATE_SNAPSHOT_SOURCE_LABEL = (
    "goal queue / decision requests / lane state / worker events / notifications"
)


def state_snapshot_schema_label(snapshot: Any) -> str | None:
    if not isinstance(snapshot, dict):
        return None
    kind = snapshot.get("kind")
    if not isinstance(kind, str) or not kind:
        return None
    schema_version = snapshot.get("schema_version")
    if isinstance(schema_version, int):
        return f"{kind} v{schema_version}"
    return kind
