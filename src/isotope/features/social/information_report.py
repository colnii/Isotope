"""Normalized information reports returned to the social loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .messages import (
    _omit_empty,
    _optional_string_value,
    _required_string_value,
)


SUPPORTED_INFORMATION_REPORT_STATUSES = {
    "completed",
    "blocked",
    "failed",
    "missing_inputs",
    "requires_operator_approval",
}


@dataclass(frozen=True)
class SocialInformationReport:
    status: str
    capability_id: str
    target: str
    reason: str
    content: str = ""
    raw_result: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in SUPPORTED_INFORMATION_REPORT_STATUSES:
            raise ValueError("information report status is not supported")
        _required_string_value(self.capability_id, "report capability_id")
        _required_string_value(self.target, "report target")
        _required_string_value(self.reason, "report reason")
        _optional_string_value(self.content, "report content")
        if not isinstance(self.raw_result, dict):
            raise ValueError("report raw_result must be a dict")

    def to_public_dict(self) -> dict[str, Any]:
        return _omit_empty(
            {
                "status": self.status,
                "capability_id": self.capability_id,
                "target": self.target,
                "reason": self.reason,
                "content": self.content,
                "raw_result": dict(self.raw_result),
            }
        )
