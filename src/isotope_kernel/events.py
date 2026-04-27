"""Canonical event boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CanonicalEvent:
    """Slice-only event envelope; this is not the final protocol schema."""

    event_id: str
    run_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CanonicalEvent":
        return cls(
            event_id=str(data["event_id"]),
            run_id=str(data["run_id"]),
            event_type=str(data["event_type"]),
            payload=dict(data.get("payload", {})),
            created_at=str(data["created_at"]),
        )
