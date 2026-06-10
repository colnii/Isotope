from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SurfaceDecision:
    eval_required: bool
    suite: str | None
    reason_codes: list[str]
    recommended_command: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eval_required": self.eval_required,
            "suite": self.suite,
            "reason_codes": list(self.reason_codes),
            "recommended_command": self.recommended_command,
        }


@dataclass(frozen=True)
class CapabilityScenario:
    case_id: str
    capability_ids: tuple[str, ...]
    user_message: str
    fixture: str
    required_gates: tuple[str, ...] = (
        "required_capacity_called",
        "low_sensitive_report",
    )
    allowed_result_statuses: tuple[str, ...] = ("ok",)
    combination_only: bool = False
    configuration_gated: bool = False
    max_turns: int = 12
