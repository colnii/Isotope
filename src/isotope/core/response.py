"""Product-level response shapes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CoreTurnResponse:
    status: str
    run_id: str
    run_status: str
    artifact_ref: dict[str, Any]
    artifact_summary: str
    event_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "run_id": self.run_id,
            "run_status": self.run_status,
            "artifact_ref": dict(self.artifact_ref),
            "artifact_summary": self.artifact_summary,
            "event_count": self.event_count,
        }
