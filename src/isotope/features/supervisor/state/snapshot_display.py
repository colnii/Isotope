"""Plain-display helpers for Supervisor state snapshots."""

from __future__ import annotations

from typing import Any


STATE_SNAPSHOT_SOURCE_LABEL = (
    "goal queue / decision requests / lane state / worker events / "
    "notifications / memory records / artifact summaries"
)
DEGRADED_SNAPSHOT_SCHEMA_LABEL = "degraded snapshot schema"


def state_snapshot_schema_status(snapshot: Any) -> dict[str, str | None]:
    if not isinstance(snapshot, dict):
        return {
            "schema_label": DEGRADED_SNAPSHOT_SCHEMA_LABEL,
            "schema_status": "degraded",
            "schema_reason": "snapshot is not an object",
        }
    kind = snapshot.get("kind")
    if not isinstance(kind, str) or not kind:
        return {
            "schema_label": DEGRADED_SNAPSHOT_SCHEMA_LABEL,
            "schema_status": "degraded",
            "schema_reason": "missing kind",
        }
    schema_version = snapshot.get("schema_version")
    if not isinstance(schema_version, int):
        return {
            "schema_label": f"{kind} degraded",
            "schema_status": "degraded",
            "schema_reason": "missing schema_version",
        }
    return {
        "schema_label": f"{kind} v{schema_version}",
        "schema_status": "ok",
        "schema_reason": None,
    }


def state_snapshot_schema_label(snapshot: Any) -> str | None:
    if not isinstance(snapshot, dict):
        return None
    return state_snapshot_schema_status(snapshot)["schema_label"]


def state_snapshot_schema_display(snapshot: Any) -> str | None:
    if snapshot is None:
        return None
    schema_status = state_snapshot_schema_status(snapshot)
    label = schema_status["schema_label"]
    reason = schema_status["schema_reason"]
    if schema_status["schema_status"] == "degraded" and reason:
        return f"{label} / {reason}"
    return label
