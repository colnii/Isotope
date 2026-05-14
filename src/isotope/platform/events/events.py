"""Canonical event boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


EVENT_ENVELOPE_VERSION = "canonical_event_slice@v0"


@dataclass(frozen=True)
class CanonicalEvent:
    """Slice-only event envelope; this is not the final protocol schema."""

    event_id: str
    run_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: str
    event_envelope_version: str = EVENT_ENVELOPE_VERSION

    def __post_init__(self) -> None:
        for field_name in ("event_id", "run_id", "event_type", "created_at", "event_envelope_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.event_envelope_version != EVENT_ENVELOPE_VERSION:
            raise ValueError("unknown event_envelope_version")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CanonicalEvent":
        if not isinstance(data, dict):
            raise ValueError("canonical event data must be a dict")
        required = ("event_id", "run_id", "event_type", "payload", "created_at")
        missing = [field_name for field_name in required if field_name not in data]
        if missing:
            raise ValueError(f"canonical event missing required fields: {', '.join(missing)}")
        return cls(
            event_id=data["event_id"],
            run_id=data["run_id"],
            event_type=data["event_type"],
            payload=data["payload"],
            created_at=data["created_at"],
            event_envelope_version=data.get("event_envelope_version", EVENT_ENVELOPE_VERSION),
        )
