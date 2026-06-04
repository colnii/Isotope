"""In-memory audit log for social bot operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .messages import _required_string_value


@dataclass(frozen=True)
class SocialAuditEntry:
    kind: str
    group_id: str
    payload: dict[str, Any]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )

    def __post_init__(self) -> None:
        _required_string_value(self.kind, "audit kind")
        _required_string_value(self.group_id, "audit group_id")
        if not isinstance(self.payload, dict):
            raise ValueError("audit payload must be a dict")
        _required_string_value(self.timestamp, "audit timestamp")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "group_id": self.group_id,
            "payload": dict(self.payload),
            "timestamp": self.timestamp,
        }


@dataclass
class SocialAuditLog:
    _entries: list[SocialAuditEntry] = field(default_factory=list)

    @property
    def entries(self) -> tuple[SocialAuditEntry, ...]:
        return tuple(self._entries)

    def append(self, kind: str, group_id: str, payload: dict[str, Any]) -> SocialAuditEntry:
        entry = SocialAuditEntry(kind=kind, group_id=group_id, payload=dict(payload))
        self._entries.append(entry)
        return entry

    def entries_for_group(self, group_id: str) -> tuple[SocialAuditEntry, ...]:
        clean_group_id = _required_string_value(group_id, "group_id")
        return tuple(entry for entry in self._entries if entry.group_id == clean_group_id)

    def counts_by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self._entries:
            counts[entry.kind] = counts.get(entry.kind, 0) + 1
        return counts
